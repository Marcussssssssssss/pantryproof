"""Synthetic-only tests for receipt-join schema and validation V0."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, replace

from evaluation.manifest_schema import (
    AuditProvenance,
    CohortDefinition,
    CohortKind,
    DatasetTier,
    EvaluationManifest,
    PartitionDefinition,
    PartitionRole,
    ReceiptManifestEntry,
    RelatedGroupKind,
    RelatedRecordGroup,
)
from evaluation.prediction_schema import (
    EvaluationRunScope,
    PredictionBundle,
    PredictionExecutionState,
    PredictionProvenance,
    PredictionReceipt,
)
from evaluation.receipt_join_schema import (
    ReceiptJoinAuthorization,
    ReceiptJoinAuthorizationState,
    ReceiptJoinEntry,
    ReceiptJoinEvidence,
    ReceiptJoinEvidenceKind,
    ReceiptJoinOutcome,
    ReceiptJoinProvenance,
    ReceiptJoinSet,
    ReceiptJoinTrustBoundaryKind,
    ReceiptJoinTrustContext,
    ReceiptJoinTrustedAuthorizationClaim,
    ReceiptJoinTrustedEntryClaim,
    ReceiptJoinVerificationEvidence,
    ReceiptJoinVerificationState,
    serialize_receipt_join_collection,
    serialize_receipt_join_set,
)
from evaluation.receipt_join_validation import (
    ReceiptJoinReadinessError,
    ReceiptJoinValidationError,
    validate_receipt_join_alignment_readiness,
    validate_receipt_join_collection,
    validate_receipt_join_set,
)
from evaluation.reference_schema import (
    REFERENCE_SCHEMA_VERSION,
    AdjudicationEventReference,
    AnnotationEventReference,
    AnnotationProvenance,
    ReferenceAvailability,
    ReferenceField,
    ReferenceRecordStatus,
    ReferenceValue,
    TierAReferenceReceipt,
)
from pipeline.contracts import (
    OutputStage,
    ReceiptExtractionStatus,
    ReceiptFieldName,
)


REFERENCE_IDS = ("reference-a", "reference-b", "reference-c", "reference-d")


def join_provenance(label: str) -> ReceiptJoinProvenance:
    return ReceiptJoinProvenance(
        event_id=f"join-event-{label}",
        process_version="synthetic-join-process-v0",
        source_references=(f"synthetic-source-{label}",),
        actor_reference="synthetic-actor",
    )


def verification(label: str) -> ReceiptJoinVerificationEvidence:
    return ReceiptJoinVerificationEvidence(
        verification_event_id=f"verify-{label}",
        verifier_reference="synthetic-verifier",
        verification_record_reference=f"synthetic-verification-{label}",
    )


def evidence(
    kind: ReceiptJoinEvidenceKind,
    label: str,
    *,
    verified: bool = False,
    unverified: bool = False,
) -> ReceiptJoinEvidence:
    if unverified:
        return ReceiptJoinEvidence(
            kind=kind,
            state=ReceiptJoinVerificationState.UNVERIFIED,
            unavailable_reason="Synthetic evidence has not been supplied.",
        )
    return ReceiptJoinEvidence(
        kind=kind,
        state=(
            ReceiptJoinVerificationState.INDEPENDENTLY_VERIFIED
            if verified
            else ReceiptJoinVerificationState.DECLARED
        ),
        evidence_references=(f"synthetic-evidence-{label}",),
        verification=verification(label) if verified else None,
    )


def authorization(*, verified: bool = False) -> ReceiptJoinAuthorization:
    return ReceiptJoinAuthorization(
        state=(
            ReceiptJoinAuthorizationState.INDEPENDENTLY_VERIFIED
            if verified
            else ReceiptJoinAuthorizationState.DECLARED
        ),
        authority_reference="synthetic-authority",
        authorization_record_reference="synthetic-authorization-record",
        verification=verification("authorization") if verified else None,
    )


def manifest() -> EvaluationManifest:
    partitions = (
        PartitionDefinition("partition-training", PartitionRole.TRAINING),
        PartitionDefinition("partition-validation", PartitionRole.VALIDATION),
        PartitionDefinition("partition-held-out", PartitionRole.HELD_OUT_TEST),
    )
    memberships = (
        ReceiptManifestEntry(
            "reference-a", "partition-training", "membership-reference-a"
        ),
        ReceiptManifestEntry(
            "reference-b", "partition-training", "membership-reference-b"
        ),
        ReceiptManifestEntry(
            "reference-c", "partition-validation", "membership-reference-c"
        ),
        ReceiptManifestEntry(
            "reference-d", "partition-held-out", "membership-reference-d"
        ),
    )
    related_groups = tuple(
        group
        for receipt_id in REFERENCE_IDS
        for group in (
            RelatedRecordGroup(
                group_id=f"transaction-{receipt_id}",
                kind=RelatedGroupKind.TRANSACTION,
                receipt_ids=(receipt_id,),
                provenance_reference=f"transaction-source-{receipt_id}",
            ),
            RelatedRecordGroup(
                group_id=f"contributor-{receipt_id}",
                kind=RelatedGroupKind.CONTRIBUTOR,
                receipt_ids=(receipt_id,),
                provenance_reference=f"contributor-source-{receipt_id}",
            ),
        )
    )
    return EvaluationManifest(
        manifest_id="synthetic-manifest",
        manifest_version="v0",
        dataset_id="synthetic-dataset",
        dataset_version="dataset-v0",
        dataset_tier=DatasetTier.TIER_A,
        annotation_version="annotation-v0",
        partitions=partitions,
        receipts=memberships,
        related_groups=related_groups,
        cohorts=(
            CohortDefinition(
                cohort_id="cohort-primary",
                kind=CohortKind.PRIMARY_TIER_A,
                dataset_id="synthetic-dataset",
                receipt_ids=REFERENCE_IDS,
                definition_reference="cohort-primary-source",
            ),
            CohortDefinition(
                cohort_id="cohort-unseen",
                kind=CohortKind.UNSEEN_RETAILER,
                dataset_id="synthetic-dataset",
                receipt_ids=("reference-b",),
                definition_reference="cohort-unseen-source",
            ),
            CohortDefinition(
                cohort_id="cohort-branch",
                kind=CohortKind.BRANCH_GENERALIZATION,
                dataset_id="synthetic-dataset",
                receipt_ids=(),
                definition_reference="cohort-branch-source",
            ),
        ),
        provenance=AuditProvenance(
            event_id="manifest-event",
            source_reference="manifest-source",
            process_version="manifest-process-v0",
        ),
    )


def reference_field(
    receipt_id: str,
    field_name: ReceiptFieldName,
    suffix: str,
) -> ReferenceField:
    return ReferenceField(
        field_id=f"{receipt_id}-{suffix}",
        receipt_id=receipt_id,
        field_name=field_name,
        availability=ReferenceAvailability.AVAILABLE,
        annotation_event_id=f"annotation-{receipt_id}",
        adjudication_event_id=f"adjudication-{receipt_id}",
        value=ReferenceValue(original_transcription=f"synthetic-{suffix}"),
    )


def reference_receipt(
    receipt_id: str,
    *,
    status: ReferenceRecordStatus = ReferenceRecordStatus.FINALIZED,
) -> TierAReferenceReceipt:
    return TierAReferenceReceipt(
        receipt_id=receipt_id,
        source_reference_id=f"source-{receipt_id}",
        provenance=AnnotationProvenance(
            schema_version=REFERENCE_SCHEMA_VERSION,
            annotation_guideline_version="synthetic-guideline-v0",
            annotation_events=(
                AnnotationEventReference(
                    event_id=f"annotation-{receipt_id}",
                    source_reference=f"annotation-source-{receipt_id}",
                ),
            ),
            adjudication_events=(
                AdjudicationEventReference(
                    event_id=f"adjudication-{receipt_id}",
                    adjudicated_reference_source=f"adjudicated-source-{receipt_id}",
                ),
            ),
        ),
        store_name=reference_field(
            receipt_id, ReceiptFieldName.STORE_NAME, "store-name"
        ),
        purchase_date=reference_field(
            receipt_id, ReceiptFieldName.PURCHASE_DATE, "purchase-date"
        ),
        items=(),
        receipt_total=reference_field(
            receipt_id, ReceiptFieldName.RECEIPT_TOTAL, "receipt-total"
        ),
        status=status,
    )


def references() -> tuple[TierAReferenceReceipt, ...]:
    return tuple(reference_receipt(receipt_id) for receipt_id in REFERENCE_IDS)


def run_scope(
    *,
    cohort_id: str = "cohort-primary",
    system_id: str = "synthetic-b2",
) -> EvaluationRunScope:
    return EvaluationRunScope(
        dataset_id="synthetic-dataset",
        dataset_tier=DatasetTier.TIER_A,
        partition_id="partition-training",
        cohort_id=cohort_id,
        run_id="synthetic-run",
        system_id=system_id,
        configuration_id="synthetic-configuration",
        output_stage=OutputStage.PRE_REVIEW_AUTOMATIC,
    )


def prediction_receipt(
    receipt_id: str,
    *,
    fallback: bool = False,
) -> PredictionReceipt:
    provenance = PredictionProvenance(
        event_id=f"prediction-event-{receipt_id}",
        source_record_reference=f"memory://synthetic/{receipt_id}",
        recorder_version="synthetic-recorder-v0",
    )
    if fallback:
        return PredictionReceipt(
            runtime_receipt_id=receipt_id,
            structured_output_present=False,
            execution_state=PredictionExecutionState.FALLBACK_NO_UPDATE,
            extraction_status=None,
            receipt_fields=(),
            rows=(),
            provenance=provenance,
            state_detail="Synthetic producer returned a fallback envelope.",
        )
    return PredictionReceipt(
        runtime_receipt_id=receipt_id,
        structured_output_present=True,
        execution_state=PredictionExecutionState.STRUCTURED_OUTPUT,
        extraction_status=ReceiptExtractionStatus.PARTIAL,
        receipt_fields=(),
        rows=(),
        provenance=provenance,
    )


def bundle(
    *,
    scope: EvaluationRunScope | None = None,
    receipt_ids: tuple[str, ...] = ("runtime-a", "runtime-extra"),
    fallback_ids: tuple[str, ...] = ("runtime-extra",),
) -> PredictionBundle:
    actual_scope = scope or run_scope()
    return PredictionBundle(
        bundle_id=f"bundle-{actual_scope.cohort_id}-{actual_scope.system_id}",
        scope=actual_scope,
        receipts=tuple(
            prediction_receipt(item, fallback=item in fallback_ids)
            for item in receipt_ids
        ),
        provenance=PredictionProvenance(
            event_id=f"bundle-event-{actual_scope.system_id}",
            source_record_reference="memory://synthetic/bundle",
            recorder_version="synthetic-recorder-v0",
        ),
    )


def join_entries(*, verified: bool = False) -> tuple[ReceiptJoinEntry, ...]:
    return (
        ReceiptJoinEntry(
            join_entry_id="entry-joined-a",
            outcome=ReceiptJoinOutcome.JOINED,
            runtime_receipt_id="runtime-a",
            reference_receipt_id="reference-a",
            evidence=evidence(
                ReceiptJoinEvidenceKind.IDENTITY_ASSOCIATION,
                "association-a",
                verified=verified,
            ),
            provenance=join_provenance("entry-joined-a"),
        ),
        ReceiptJoinEntry(
            join_entry_id="entry-reference-b",
            outcome=ReceiptJoinOutcome.REFERENCE_ONLY,
            runtime_receipt_id=None,
            reference_receipt_id="reference-b",
            evidence=evidence(
                ReceiptJoinEvidenceKind.COVERAGE_ABSENCE,
                "coverage-reference-b",
                verified=verified,
            ),
            provenance=join_provenance("entry-reference-b"),
            unmatched_reason="No prediction receipt is present in the scoped bundle.",
        ),
        ReceiptJoinEntry(
            join_entry_id="entry-prediction-extra",
            outcome=ReceiptJoinOutcome.PREDICTION_ONLY,
            runtime_receipt_id="runtime-extra",
            reference_receipt_id=None,
            evidence=evidence(
                ReceiptJoinEvidenceKind.COVERAGE_ABSENCE,
                "coverage-prediction-extra",
                verified=verified,
            ),
            provenance=join_provenance("entry-prediction-extra"),
            unmatched_reason="No selected reference identity is associated.",
        ),
    )


def join_set(
    *,
    prediction_bundle: PredictionBundle | None = None,
    entries: tuple[ReceiptJoinEntry, ...] | None = None,
    verified: bool = False,
    join_set_id: str = "join-set-primary",
    join_set_version: str = "v0",
    revision_id: str = "join-revision-0",
    predecessor_revision_id: str | None = None,
) -> ReceiptJoinSet:
    actual_bundle = prediction_bundle or bundle()
    return ReceiptJoinSet(
        join_set_id=join_set_id,
        join_set_version=join_set_version,
        revision_id=revision_id,
        manifest_id="synthetic-manifest",
        manifest_version="v0",
        dataset_version="dataset-v0",
        prediction_bundle_id=actual_bundle.bundle_id,
        prediction_scope=actual_bundle.scope,
        entries=entries if entries is not None else join_entries(verified=verified),
        authorization=authorization(verified=verified),
        provenance=join_provenance(revision_id),
        predecessor_revision_id=predecessor_revision_id,
        amendment_reason=(
            "Synthetic correction of a declared association."
            if predecessor_revision_id is not None
            else None
        ),
        amendment_provenance=(
            join_provenance(f"amend-{revision_id}")
            if predecessor_revision_id is not None
            else None
        ),
    )


def trust_context(item: ReceiptJoinSet | None = None) -> ReceiptJoinTrustContext:
    bound_join_set = item or join_set(verified=True)
    entry_claims = []
    for entry in bound_join_set.entries:
        assert entry.evidence.verification is not None
        entry_claims.append(
            ReceiptJoinTrustedEntryClaim(
                claim_id=f"trusted-{entry.join_entry_id}",
                verification=replace(entry.evidence.verification),
                manifest_id=bound_join_set.manifest_id,
                manifest_version=bound_join_set.manifest_version,
                dataset_version=bound_join_set.dataset_version,
                prediction_bundle_id=bound_join_set.prediction_bundle_id,
                prediction_scope=bound_join_set.prediction_scope,
                join_set_id=bound_join_set.join_set_id,
                join_set_version=bound_join_set.join_set_version,
                revision_id=bound_join_set.revision_id,
                join_entry_id=entry.join_entry_id,
                outcome=entry.outcome,
                runtime_receipt_id=entry.runtime_receipt_id,
                reference_receipt_id=entry.reference_receipt_id,
                evidence_references=entry.evidence.evidence_references,
            )
        )
    assert bound_join_set.authorization.verification is not None
    authorization_claim = ReceiptJoinTrustedAuthorizationClaim(
        claim_id="trusted-authorization",
        verification=replace(bound_join_set.authorization.verification),
        manifest_id=bound_join_set.manifest_id,
        manifest_version=bound_join_set.manifest_version,
        dataset_version=bound_join_set.dataset_version,
        prediction_bundle_id=bound_join_set.prediction_bundle_id,
        prediction_scope=bound_join_set.prediction_scope,
        join_set_id=bound_join_set.join_set_id,
        join_set_version=bound_join_set.join_set_version,
        revision_id=bound_join_set.revision_id,
        authority_reference=bound_join_set.authorization.authority_reference or "",
        authorization_record_reference=(
            bound_join_set.authorization.authorization_record_reference or ""
        ),
    )
    return ReceiptJoinTrustContext(
        context_id="synthetic-trust-context",
        boundary_kind=ReceiptJoinTrustBoundaryKind.SYNTHETIC_FIXTURE,
        entry_claims=tuple(entry_claims),
        authorization_claims=(authorization_claim,),
        provenance=join_provenance("trust-context"),
    )


class ReceiptJoinSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = manifest()
        self.references = references()
        self.bundle = bundle()

    def validate(self, item: ReceiptJoinSet) -> None:
        validate_receipt_join_set(
            item,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )

    def test_all_three_outcomes_cover_both_populations_once(self) -> None:
        item = join_set(prediction_bundle=self.bundle)
        self.validate(item)
        self.assertEqual(
            {item.outcome for item in item.entries}, set(ReceiptJoinOutcome)
        )

    def test_runtime_and_reference_identifiers_remain_independent(self) -> None:
        item = join_set(prediction_bundle=self.bundle)
        joined = item.entries[0]
        self.assertNotEqual(joined.runtime_receipt_id, joined.reference_receipt_id)
        self.assertFalse(hasattr(self.bundle.receipts[0], "reference_receipt_id"))

    def test_fallback_and_structured_empty_receipts_are_preserved(self) -> None:
        item = join_set(prediction_bundle=self.bundle)
        self.validate(item)
        self.assertTrue(self.bundle.receipts[0].structured_output_present)
        self.assertEqual(self.bundle.receipts[0].rows, ())
        self.assertFalse(self.bundle.receipts[1].structured_output_present)
        self.assertEqual(
            self.bundle.receipts[1].execution_state,
            PredictionExecutionState.FALLBACK_NO_UPDATE,
        )

    def test_reference_only_does_not_fabricate_runtime_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not fabricate"):
            replace(join_entries()[1], runtime_receipt_id="invented-runtime")

    def test_prediction_only_does_not_fabricate_reference_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not fabricate"):
            replace(join_entries()[2], reference_receipt_id="invented-reference")

    def test_joined_requires_association_evidence_kind(self) -> None:
        with self.assertRaisesRegex(ValueError, "identity-association"):
            replace(
                join_entries()[0],
                evidence=evidence(
                    ReceiptJoinEvidenceKind.COVERAGE_ABSENCE, "wrong-kind"
                ),
            )

    def test_unmatched_requires_coverage_absence_evidence_kind(self) -> None:
        with self.assertRaisesRegex(ValueError, "coverage/absence"):
            replace(
                join_entries()[1],
                evidence=evidence(
                    ReceiptJoinEvidenceKind.IDENTITY_ASSOCIATION, "wrong-kind"
                ),
            )

    def test_missing_prediction_coverage_is_rejected(self) -> None:
        item = join_set(
            prediction_bundle=self.bundle,
            entries=join_entries()[:-1],
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "prediction population"):
            self.validate(item)

    def test_missing_reference_coverage_is_rejected(self) -> None:
        item = join_set(
            prediction_bundle=self.bundle,
            entries=(join_entries()[0], join_entries()[2]),
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "reference population"):
            self.validate(item)

    def test_duplicate_runtime_mapping_is_rejected(self) -> None:
        duplicate = replace(
            join_entries()[2], runtime_receipt_id="runtime-a"
        )
        item = join_set(
            prediction_bundle=self.bundle,
            entries=(join_entries()[0], join_entries()[1], duplicate),
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "more than once"):
            self.validate(item)

    def test_duplicate_join_entry_identity_is_rejected(self) -> None:
        duplicate = replace(
            join_entries()[2], join_entry_id="entry-reference-b"
        )
        item = join_set(
            prediction_bundle=self.bundle,
            entries=(join_entries()[0], join_entries()[1], duplicate),
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "Duplicate join entry"):
            self.validate(item)

    def test_duplicate_reference_mapping_is_rejected(self) -> None:
        duplicate = replace(
            join_entries()[1], reference_receipt_id="reference-a"
        )
        item = join_set(
            prediction_bundle=self.bundle,
            entries=(join_entries()[0], duplicate, join_entries()[2]),
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "more than once"):
            self.validate(item)

    def test_substituted_runtime_identity_is_rejected(self) -> None:
        substituted = replace(
            join_entries()[0], runtime_receipt_id="runtime-unknown"
        )
        item = join_set(
            prediction_bundle=self.bundle,
            entries=(substituted, *join_entries()[1:]),
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "unknown runtime"):
            self.validate(item)

    def test_reference_outside_partition_cohort_intersection_is_rejected(self) -> None:
        unseen_scope = run_scope(cohort_id="cohort-unseen")
        unseen_bundle = bundle(
            scope=unseen_scope,
            receipt_ids=("runtime-b",),
            fallback_ids=(),
        )
        wrong = ReceiptJoinEntry(
            join_entry_id="wrong-reference-a",
            outcome=ReceiptJoinOutcome.JOINED,
            runtime_receipt_id="runtime-b",
            reference_receipt_id="reference-a",
            evidence=evidence(
                ReceiptJoinEvidenceKind.IDENTITY_ASSOCIATION, "wrong-reference"
            ),
            provenance=join_provenance("wrong-reference"),
        )
        item = join_set(prediction_bundle=unseen_bundle, entries=(wrong,))
        with self.assertRaisesRegex(
            ReceiptJoinValidationError, "partition/cohort intersection"
        ):
            validate_receipt_join_set(
                item,
                manifest=self.manifest,
                prediction_bundle=unseen_bundle,
                reference_receipts=self.references,
            )

    def test_exact_partition_cohort_intersection_is_accepted(self) -> None:
        unseen_scope = run_scope(cohort_id="cohort-unseen")
        unseen_bundle = bundle(
            scope=unseen_scope,
            receipt_ids=("runtime-b",),
            fallback_ids=(),
        )
        entry = ReceiptJoinEntry(
            join_entry_id="joined-reference-b",
            outcome=ReceiptJoinOutcome.JOINED,
            runtime_receipt_id="runtime-b",
            reference_receipt_id="reference-b",
            evidence=evidence(
                ReceiptJoinEvidenceKind.IDENTITY_ASSOCIATION, "reference-b"
            ),
            provenance=join_provenance("reference-b"),
        )
        item = join_set(prediction_bundle=unseen_bundle, entries=(entry,))
        validate_receipt_join_set(
            item,
            manifest=self.manifest,
            prediction_bundle=unseen_bundle,
            reference_receipts=self.references,
        )

    def test_manifest_and_bundle_scope_conflicts_are_rejected(self) -> None:
        item = replace(join_set(prediction_bundle=self.bundle), manifest_version="v9")
        with self.assertRaisesRegex(ReceiptJoinValidationError, "manifest version"):
            self.validate(item)
        other_scope = run_scope(system_id="synthetic-b3")
        scope_substitution = replace(item, manifest_version="v0", prediction_scope=other_scope)
        with self.assertRaisesRegex(ReceiptJoinValidationError, "complete prediction"):
            self.validate(scope_substitution)

    def test_equal_identifier_text_does_not_supply_mapping_evidence(self) -> None:
        equal_bundle = bundle(
            receipt_ids=("reference-a", "runtime-extra"),
            fallback_ids=("runtime-extra",),
        )
        equal_join = replace(
            join_entries()[0],
            runtime_receipt_id="reference-a",
            evidence=evidence(
                ReceiptJoinEvidenceKind.IDENTITY_ASSOCIATION,
                "equal-ids",
                unverified=True,
            ),
        )
        item = join_set(
            prediction_bundle=equal_bundle,
            entries=(equal_join, *join_entries()[1:]),
            verified=True,
        )
        validate_receipt_join_set(
            item,
            manifest=self.manifest,
            prediction_bundle=equal_bundle,
            reference_receipts=self.references,
        )
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "verified evidence"):
            validate_receipt_join_alignment_readiness(
                item,
                manifest=self.manifest,
                prediction_bundle=equal_bundle,
                reference_receipts=self.references,
                trust_context=trust_context(),
            )

    def test_structural_validity_does_not_establish_readiness(self) -> None:
        item = join_set(prediction_bundle=self.bundle)
        self.validate(item)
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "authorization"):
            validate_receipt_join_alignment_readiness(
                item,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
                trust_context=trust_context(),
            )

    def test_verified_strings_not_registered_by_trust_boundary_fail_closed(self) -> None:
        item = join_set(prediction_bundle=self.bundle, verified=True)
        incomplete_trust = replace(
            trust_context(item), entry_claims=trust_context(item).entry_claims[1:]
        )
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "no external trusted"):
            validate_receipt_join_alignment_readiness(
                item,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
                trust_context=incomplete_trust,
            )

    def test_explicit_synthetic_trust_context_can_pass_synthetic_readiness(self) -> None:
        item = join_set(prediction_bundle=self.bundle, verified=True)
        validate_receipt_join_alignment_readiness(
            item,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
            trust_context=trust_context(item),
        )

    def test_swapped_association_rejects_old_trusted_claims(self) -> None:
        original = join_set(prediction_bundle=self.bundle, verified=True)
        original_trust = trust_context(original)
        swapped_joined = replace(
            original.entries[0], reference_receipt_id="reference-b"
        )
        swapped_reference_only = replace(
            original.entries[1], reference_receipt_id="reference-a"
        )
        swapped = replace(
            original,
            entries=(
                swapped_joined,
                swapped_reference_only,
                original.entries[2],
            ),
        )
        self.validate(swapped)
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "another identity"):
            validate_receipt_join_alignment_readiness(
                swapped,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
                trust_context=original_trust,
            )

    def test_trusted_events_cannot_cross_system_or_bundle_scope(self) -> None:
        original = join_set(prediction_bundle=self.bundle, verified=True)
        other_bundle = bundle(scope=run_scope(system_id="synthetic-b3"))
        other = join_set(prediction_bundle=other_bundle, verified=True)
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "another scope"):
            validate_receipt_join_alignment_readiness(
                other,
                manifest=self.manifest,
                prediction_bundle=other_bundle,
                reference_receipts=self.references,
                trust_context=trust_context(original),
            )

    def test_trusted_events_cannot_cross_join_set_revisions(self) -> None:
        initial = join_set(prediction_bundle=self.bundle, verified=True)
        successor = join_set(
            prediction_bundle=self.bundle,
            verified=True,
            join_set_version="v1",
            revision_id="join-revision-1",
            predecessor_revision_id="join-revision-0",
        )
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "another scope"):
            validate_receipt_join_alignment_readiness(
                successor,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
                trust_context=trust_context(initial),
            )

    def test_one_trusted_event_cannot_support_unrelated_entry_claims(self) -> None:
        item = join_set(prediction_bundle=self.bundle, verified=True)
        joined_verification = item.entries[0].evidence.verification
        assert joined_verification is not None
        reused_evidence = replace(
            item.entries[1].evidence, verification=joined_verification
        )
        reused = replace(
            item,
            entries=(
                item.entries[0],
                replace(item.entries[1], evidence=reused_evidence),
                item.entries[2],
            ),
        )
        self.validate(reused)
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "another identity"):
            validate_receipt_join_alignment_readiness(
                reused,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
                trust_context=trust_context(item),
            )

    def test_consumption_rejects_mutated_schema_version(self) -> None:
        item = join_set(prediction_bundle=self.bundle)
        object.__setattr__(item, "schema_version", "mutated-version")
        with self.assertRaisesRegex(ReceiptJoinValidationError, "schema"):
            self.validate(item)

    def test_consumption_rejects_removed_unmatched_reason(self) -> None:
        item = join_set(prediction_bundle=self.bundle)
        object.__setattr__(item.entries[1], "unmatched_reason", None)
        with self.assertRaisesRegex(ReceiptJoinValidationError, "unmatched_reason"):
            self.validate(item)

    def test_consumption_rejects_string_replacing_enum(self) -> None:
        item = join_set(prediction_bundle=self.bundle)
        object.__setattr__(item.entries[0], "outcome", "JOINED")
        with self.assertRaisesRegex(ReceiptJoinValidationError, "ReceiptJoinOutcome"):
            self.validate(item)

    def test_consumption_rejects_invalid_nested_verification_and_authorization(self) -> None:
        with self.subTest("verification"):
            item = join_set(prediction_bundle=self.bundle, verified=True)
            nested_verification = item.entries[0].evidence.verification
            assert nested_verification is not None
            object.__setattr__(nested_verification, "verifier_reference", "")
            with self.assertRaisesRegex(
                ReceiptJoinValidationError, "verification.*invariants"
            ):
                self.validate(item)

        with self.subTest("authorization"):
            item = join_set(prediction_bundle=self.bundle, verified=True)
            object.__setattr__(
                item.authorization,
                "state",
                ReceiptJoinAuthorizationState.DECLARED,
            )
            with self.assertRaisesRegex(
                ReceiptJoinValidationError, "authorization.*invariants"
            ):
                self.validate(item)

    def test_consumption_rejects_mutated_trusted_claim(self) -> None:
        item = join_set(prediction_bundle=self.bundle, verified=True)
        context = trust_context(item)
        object.__setattr__(context.entry_claims[0], "outcome", "JOINED")
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "trusted entry claim"):
            validate_receipt_join_alignment_readiness(
                item,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
                trust_context=context,
            )

    def test_draft_selected_reference_blocks_readiness_only(self) -> None:
        item = join_set(prediction_bundle=self.bundle, verified=True)
        draft_references = (
            reference_receipt("reference-a", status=ReferenceRecordStatus.DRAFT),
            *self.references[1:],
        )
        validate_receipt_join_set(
            item,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=draft_references,
        )
        with self.assertRaisesRegex(ReceiptJoinReadinessError, "not finalized"):
            validate_receipt_join_alignment_readiness(
                item,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=draft_references,
                trust_context=trust_context(),
            )

    def test_deterministic_serialization_canonicalizes_entry_order(self) -> None:
        first = join_set(prediction_bundle=self.bundle)
        reconstructed = replace(first, entries=tuple(reversed(first.entries)))
        first_json = serialize_receipt_join_set(
            first,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )
        second_json = serialize_receipt_join_set(
            reconstructed,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )
        self.assertEqual(first_json, second_json)
        payload = json.loads(first_json)
        self.assertEqual(payload["schema_version"], "0")
        self.assertIsNone(payload["predecessor_revision_id"])

    def test_records_are_frozen(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            join_set(prediction_bundle=self.bundle).revision_id = "changed"  # type: ignore[misc]

    def test_valid_append_only_revision_lineage_is_preserved(self) -> None:
        initial = join_set(prediction_bundle=self.bundle)
        successor = join_set(
            prediction_bundle=self.bundle,
            join_set_version="v1",
            revision_id="join-revision-1",
            predecessor_revision_id="join-revision-0",
        )
        validate_receipt_join_collection(
            (successor, initial),
            manifests=(self.manifest,),
            prediction_bundles=(self.bundle,),
            reference_receipts=self.references,
        )
        payload = json.loads(
            serialize_receipt_join_collection(
                (successor, initial),
                manifests=(self.manifest,),
                prediction_bundles=(self.bundle,),
                reference_receipts=self.references,
            )
        )
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[1]["predecessor_revision_id"], "join-revision-0")

    def test_broken_revision_lineage_is_rejected(self) -> None:
        successor = join_set(
            prediction_bundle=self.bundle,
            join_set_version="v1",
            revision_id="join-revision-1",
            predecessor_revision_id="missing-revision",
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "broken predecessor"):
            validate_receipt_join_collection(
                (successor,),
                manifests=(self.manifest,),
                prediction_bundles=(self.bundle,),
                reference_receipts=self.references,
            )

    def test_cyclic_revision_lineage_is_rejected(self) -> None:
        first = join_set(
            prediction_bundle=self.bundle,
            join_set_version="v0",
            revision_id="join-revision-0",
            predecessor_revision_id="join-revision-1",
        )
        second = join_set(
            prediction_bundle=self.bundle,
            join_set_version="v1",
            revision_id="join-revision-1",
            predecessor_revision_id="join-revision-0",
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "cycle"):
            validate_receipt_join_collection(
                (first, second),
                manifests=(self.manifest,),
                prediction_bundles=(self.bundle,),
                reference_receipts=self.references,
            )

    def test_conflicting_successor_heads_are_rejected(self) -> None:
        initial = join_set(prediction_bundle=self.bundle)
        child_one = join_set(
            prediction_bundle=self.bundle,
            join_set_version="v1",
            revision_id="join-revision-1",
            predecessor_revision_id="join-revision-0",
        )
        child_two = join_set(
            prediction_bundle=self.bundle,
            join_set_version="v2",
            revision_id="join-revision-2",
            predecessor_revision_id="join-revision-0",
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "conflicting"):
            validate_receipt_join_collection(
                (initial, child_one, child_two),
                manifests=(self.manifest,),
                prediction_bundles=(self.bundle,),
                reference_receipts=self.references,
            )

    def test_unrelated_current_heads_for_one_scope_are_rejected(self) -> None:
        first = join_set(prediction_bundle=self.bundle)
        second = join_set(
            prediction_bundle=self.bundle,
            join_set_id="parallel-join-set",
            revision_id="parallel-revision-0",
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "current join-set heads"):
            validate_receipt_join_collection(
                (first, second),
                manifests=(self.manifest,),
                prediction_bundles=(self.bundle,),
                reference_receipts=self.references,
            )

    def test_duplicate_revision_identity_is_rejected(self) -> None:
        first = join_set(prediction_bundle=self.bundle)
        duplicate = join_set(
            prediction_bundle=self.bundle,
            join_set_id="parallel-join-set",
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "Duplicate join-set revision"):
            validate_receipt_join_collection(
                (first, duplicate),
                manifests=(self.manifest,),
                prediction_bundles=(self.bundle,),
                reference_receipts=self.references,
            )

    def test_revision_cannot_substitute_another_prediction_scope(self) -> None:
        initial = join_set(prediction_bundle=self.bundle)
        other_bundle = bundle(scope=run_scope(system_id="synthetic-b3"))
        successor = join_set(
            prediction_bundle=other_bundle,
            join_set_version="v1",
            revision_id="join-revision-1",
            predecessor_revision_id="join-revision-0",
        )
        with self.assertRaisesRegex(ReceiptJoinValidationError, "immutable source scope"):
            validate_receipt_join_collection(
                (initial, successor),
                manifests=(self.manifest,),
                prediction_bundles=(self.bundle, other_bundle),
                reference_receipts=self.references,
            )

    def test_undocumented_or_unauthorized_amendment_is_rejected(self) -> None:
        initial = join_set(prediction_bundle=self.bundle)
        with self.assertRaisesRegex(ValueError, "amendment provenance"):
            replace(
                initial,
                join_set_version="v1",
                revision_id="join-revision-1",
                predecessor_revision_id="join-revision-0",
                amendment_reason="Synthetic amendment.",
            )
        unavailable = ReceiptJoinAuthorization(
            state=ReceiptJoinAuthorizationState.UNAVAILABLE,
            unavailable_reason="No authorization supplied.",
        )
        with self.assertRaisesRegex(ValueError, "declared authorization"):
            replace(
                initial,
                join_set_version="v1",
                revision_id="join-revision-1",
                predecessor_revision_id="join-revision-0",
                amendment_reason="Synthetic amendment.",
                amendment_provenance=join_provenance("amendment"),
                authorization=unavailable,
            )


if __name__ == "__main__":
    unittest.main()
