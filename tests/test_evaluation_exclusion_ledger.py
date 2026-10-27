"""Synthetic-only tests for the offline exclusion/reason ledger V0."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from evaluation.exclusion_ledger import (
    DenominatorAction,
    ExclusionCategory,
    ExclusionLedger,
    ExclusionLedgerEntry,
    ExclusionLedgerValidationError,
    LedgerReasonCode,
    LedgerStage,
    serialize_exclusion_ledger,
    validate_exclusion_ledger,
)
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
from evaluation.reference_schema import (
    REFERENCE_SCHEMA_VERSION,
    AdjudicationEventReference,
    AnnotationEventReference,
    AnnotationProvenance,
    ReferenceAvailability,
    ReferenceField,
    ReferenceItemRow,
    ReferenceRecordStatus,
    ReferenceValue,
    TierAReferenceReceipt,
)
from pipeline.contracts import ReceiptFieldName


RECEIPT_ID = "synthetic-ledger-receipt"
ANNOTATION_EVENT = "synthetic-ledger-annotation"
ADJUDICATION_EVENT = "synthetic-ledger-adjudication"


def audit(event_id: str = "synthetic-ledger-event") -> AuditProvenance:
    return AuditProvenance(
        event_id=event_id,
        source_reference=f"source-{event_id}",
        process_version="synthetic-ledger-process-v0",
    )


def field(
    field_id: str,
    field_name: ReceiptFieldName,
    value: str | None,
    *,
    row_id: str | None = None,
    unavailable_reason: str | None = None,
) -> ReferenceField:
    available = value is not None
    return ReferenceField(
        field_id=field_id,
        receipt_id=RECEIPT_ID,
        field_name=field_name,
        availability=(
            ReferenceAvailability.AVAILABLE
            if available
            else ReferenceAvailability.UNAVAILABLE
        ),
        annotation_event_id=ANNOTATION_EVENT,
        adjudication_event_id=ADJUDICATION_EVENT,
        item_row_id=row_id,
        value=ReferenceValue(value) if available else None,
        unavailable_reason=unavailable_reason,
    )


def reference_receipt(
    *,
    unit_price_available: bool = True,
    status: ReferenceRecordStatus = ReferenceRecordStatus.FINALIZED,
) -> TierAReferenceReceipt:
    row_id = "row-1"
    unit_price = field(
        "field-unit-price",
        ReceiptFieldName.UNIT_PRICE,
        "RM 5.00" if unit_price_available else None,
        row_id=row_id,
        unavailable_reason=None
        if unit_price_available
        else "Unit price is neither printed nor derivable under the synthetic rule.",
    )
    if status is ReferenceRecordStatus.DRAFT:
        unit_price = replace(unit_price, adjudication_event_id=None)
    row = ReferenceItemRow(
        row_id=row_id,
        receipt_id=RECEIPT_ID,
        source_order=0,
        description=field(
            "field-description",
            ReceiptFieldName.ITEM_DESCRIPTION,
            "SYNTHETIC ITEM",
            row_id=row_id,
        ),
        quantity=field(
            "field-quantity", ReceiptFieldName.QUANTITY, "1", row_id=row_id
        ),
        unit_price=unit_price,
        line_total=field(
            "field-line-total",
            ReceiptFieldName.LINE_TOTAL,
            "RM 5.00",
            row_id=row_id,
        ),
    )
    return TierAReferenceReceipt(
        receipt_id=RECEIPT_ID,
        source_reference_id="synthetic-ledger-source-image",
        provenance=AnnotationProvenance(
            schema_version=REFERENCE_SCHEMA_VERSION,
            annotation_guideline_version="synthetic-guideline-v0",
            annotation_events=(
                AnnotationEventReference(
                    ANNOTATION_EVENT, "synthetic-annotation-source"
                ),
            ),
            adjudication_events=(
                AdjudicationEventReference(
                    ADJUDICATION_EVENT, "synthetic-adjudicated-source"
                ),
            ),
        ),
        store_name=field(
            "field-store", ReceiptFieldName.STORE_NAME, "SYNTHETIC STORE"
        ),
        purchase_date=field(
            "field-date", ReceiptFieldName.PURCHASE_DATE, "2026-10-27"
        ),
        items=(row,),
        receipt_total=field(
            "field-receipt-total", ReceiptFieldName.RECEIPT_TOTAL, "RM 5.00"
        ),
        status=status,
    )


def manifest() -> EvaluationManifest:
    return EvaluationManifest(
        manifest_id="synthetic-ledger-manifest",
        manifest_version="0",
        dataset_id="synthetic-ledger-dataset",
        dataset_version="synthetic-ledger-dataset-v0",
        dataset_tier=DatasetTier.TIER_A,
        annotation_version="synthetic-guideline-v0",
        partitions=(
            PartitionDefinition("partition-training", PartitionRole.TRAINING),
            PartitionDefinition("partition-validation", PartitionRole.VALIDATION),
            PartitionDefinition("partition-held-out", PartitionRole.HELD_OUT_TEST),
        ),
        receipts=(
            ReceiptManifestEntry(
                RECEIPT_ID,
                "partition-training",
                "synthetic-ledger-membership",
            ),
        ),
        related_groups=(
            RelatedRecordGroup(
                "transaction-ledger",
                RelatedGroupKind.TRANSACTION,
                (RECEIPT_ID,),
                "synthetic-transaction-group",
            ),
            RelatedRecordGroup(
                "contributor-ledger",
                RelatedGroupKind.CONTRIBUTOR,
                (RECEIPT_ID,),
                "synthetic-contributor-group",
            ),
        ),
        cohorts=(
            CohortDefinition(
                "cohort-primary",
                CohortKind.PRIMARY_TIER_A,
                "synthetic-ledger-dataset",
                (RECEIPT_ID,),
                "synthetic-primary-cohort",
            ),
            CohortDefinition(
                "cohort-unseen-retailer",
                CohortKind.UNSEEN_RETAILER,
                "synthetic-ledger-dataset",
                (),
                "synthetic-unseen-cohort",
            ),
            CohortDefinition(
                "cohort-branch-generalization",
                CohortKind.BRANCH_GENERALIZATION,
                "synthetic-ledger-dataset",
                (),
                "synthetic-branch-cohort",
            ),
        ),
        provenance=audit("synthetic-manifest-audit"),
    )


def ledger_entry(
    *,
    entry_id: str,
    category: ExclusionCategory,
    stage: LedgerStage,
    reason: LedgerReasonCode,
    action: DenominatorAction,
    field_id: str | None = None,
    row_id: str | None = None,
    receipt_id: str | None = RECEIPT_ID,
    partition_id: str | None = "partition-training",
    cohort_id: str | None = "cohort-primary",
    run_id: str | None = None,
    system_id: str | None = None,
) -> ExclusionLedgerEntry:
    return ExclusionLedgerEntry(
        ledger_entry_id=entry_id,
        dataset_id="synthetic-ledger-dataset",
        dataset_tier=DatasetTier.TIER_A,
        partition_id=partition_id,
        cohort_id=cohort_id,
        receipt_id=receipt_id,
        item_row_id=row_id,
        field_id=field_id,
        stage=stage,
        category=category,
        reason_code=reason,
        reason_detail="Synthetic reason detail only.",
        affected_metrics=("synthetic-metric",),
        denominator_action=action,
        run_id=run_id,
        system_id=system_id,
        audit_provenance=audit(f"audit-{entry_id}"),
        software_version="synthetic-evaluator-v0",
    )


def ledger(*entries: ExclusionLedgerEntry) -> ExclusionLedger:
    return ExclusionLedger(
        ledger_id="synthetic-exclusion-ledger",
        ledger_version="0",
        manifest_id="synthetic-ledger-manifest",
        dataset_id="synthetic-ledger-dataset",
        dataset_tier=DatasetTier.TIER_A,
        entries=entries,
        provenance=audit("synthetic-ledger-envelope"),
    )


class ExclusionLedgerTests(unittest.TestCase):
    def test_dataset_exclusion_requires_receipt_identity(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "DATASET_LEVEL_EXCLUSION requires receipt_id"
        ):
            ledger_entry(
                entry_id="dataset-exclusion-without-receipt",
                category=ExclusionCategory.DATASET_LEVEL_EXCLUSION,
                stage=LedgerStage.DATASET_ELIGIBILITY,
                reason=LedgerReasonCode.DATASET_INELIGIBLE,
                action=DenominatorAction.EXCLUDE_FROM_DATASET,
                receipt_id=None,
                partition_id=None,
                cohort_id=None,
            )

    def test_dataset_exclusion_rejects_member_but_allows_nonmember(self) -> None:
        member_exclusion = ledger_entry(
            entry_id="member-dataset-exclusion",
            category=ExclusionCategory.DATASET_LEVEL_EXCLUSION,
            stage=LedgerStage.DATASET_ELIGIBILITY,
            reason=LedgerReasonCode.DATASET_INELIGIBLE,
            action=DenominatorAction.EXCLUDE_FROM_DATASET,
            partition_id=None,
            cohort_id=None,
        )
        with self.assertRaisesRegex(
            ExclusionLedgerValidationError, "eligible manifest membership"
        ):
            validate_exclusion_ledger(
                ledger(member_exclusion), manifest=manifest()
            )

        nonmember_exclusion = replace(
            member_exclusion,
            ledger_entry_id="nonmember-dataset-exclusion",
            receipt_id="prospectively-ineligible-receipt",
        )
        validate_exclusion_ledger(
            ledger(nonmember_exclusion), manifest=manifest()
        )

    def test_missing_prediction_is_retained_as_evaluation_error(self) -> None:
        receipt = reference_receipt()
        entry = ledger_entry(
            entry_id="missing-prediction",
            category=ExclusionCategory.SYSTEM_MISSING_PREDICTION,
            stage=LedgerStage.PREDICTION,
            reason=LedgerReasonCode.PREDICTION_ABSENT,
            action=DenominatorAction.INCLUDE_AS_EVALUATION_ERROR,
            field_id="field-quantity",
            row_id="row-1",
            run_id="synthetic-run",
            system_id="synthetic-system",
        )

        validate_exclusion_ledger(
            ledger(entry), manifest=manifest(), references=(receipt,)
        )
        self.assertIs(
            entry.denominator_action, DenominatorAction.INCLUDE_AS_EVALUATION_ERROR
        )

    def test_missing_prediction_cannot_be_recategorized_as_an_exclusion(self) -> None:
        for category, stage, action in (
            (
                ExclusionCategory.DATASET_LEVEL_EXCLUSION,
                LedgerStage.DATASET_ELIGIBILITY,
                DenominatorAction.EXCLUDE_FROM_DATASET,
            ),
            (
                ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
                LedgerStage.REFERENCE_ANNOTATION,
                DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
            ),
        ):
            with self.subTest(category=category):
                with self.assertRaisesRegex(ValueError, "reason code"):
                    ledger_entry(
                        entry_id=f"invalid-{category.value.lower()}",
                        category=category,
                        stage=stage,
                        reason=LedgerReasonCode.PREDICTION_ABSENT,
                        action=action,
                        field_id="field-quantity",
                        row_id="row-1",
                    )

    def test_missing_prediction_cannot_use_exclusion_denominator_action(self) -> None:
        with self.assertRaisesRegex(ValueError, "denominator action"):
            ledger_entry(
                entry_id="missing-prediction-wrong-action",
                category=ExclusionCategory.SYSTEM_MISSING_PREDICTION,
                stage=LedgerStage.PREDICTION,
                reason=LedgerReasonCode.PREDICTION_ABSENT,
                action=DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
                field_id="field-quantity",
                row_id="row-1",
                run_id="synthetic-run",
                system_id="synthetic-system",
            )

    def test_genuine_reference_unavailability_uses_independent_truth(self) -> None:
        receipt = reference_receipt(unit_price_available=False)
        entry = ledger_entry(
            entry_id="unit-price-unavailable",
            category=ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
            stage=LedgerStage.REFERENCE_ANNOTATION,
            reason=LedgerReasonCode.UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE,
            action=DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
            field_id="field-unit-price",
            row_id="row-1",
        )
        validate_exclusion_ledger(
            ledger(entry), manifest=manifest(), references=(receipt,)
        )

    def test_truth_dependent_assertions_reject_unadjudicated_field(self) -> None:
        unadjudicated_available = reference_receipt(
            status=ReferenceRecordStatus.DRAFT
        )
        missing_prediction = ledger_entry(
            entry_id="unadjudicated-missing-prediction",
            category=ExclusionCategory.SYSTEM_MISSING_PREDICTION,
            stage=LedgerStage.PREDICTION,
            reason=LedgerReasonCode.PREDICTION_ABSENT,
            action=DenominatorAction.INCLUDE_AS_EVALUATION_ERROR,
            field_id="field-unit-price",
            row_id="row-1",
            run_id="synthetic-run",
            system_id="synthetic-system",
        )
        with self.assertRaisesRegex(
            ExclusionLedgerValidationError, "field-level adjudication"
        ):
            validate_exclusion_ledger(
                ledger(missing_prediction), references=(unadjudicated_available,)
            )

        unadjudicated_unavailable = reference_receipt(
            unit_price_available=False,
            status=ReferenceRecordStatus.DRAFT,
        )
        unavailable = ledger_entry(
            entry_id="unadjudicated-reference-unavailable",
            category=ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
            stage=LedgerStage.REFERENCE_ANNOTATION,
            reason=LedgerReasonCode.UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE,
            action=DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
            field_id="field-unit-price",
            row_id="row-1",
        )
        with self.assertRaisesRegex(
            ExclusionLedgerValidationError, "field-level adjudication"
        ):
            validate_exclusion_ledger(
                ledger(unavailable), references=(unadjudicated_unavailable,)
            )

    def test_adjudicated_field_can_be_checked_while_unrelated_field_is_pending(self) -> None:
        draft = reference_receipt(status=ReferenceRecordStatus.DRAFT)
        missing_quantity = ledger_entry(
            entry_id="adjudicated-quantity-missing",
            category=ExclusionCategory.SYSTEM_MISSING_PREDICTION,
            stage=LedgerStage.PREDICTION,
            reason=LedgerReasonCode.PREDICTION_ABSENT,
            action=DenominatorAction.INCLUDE_AS_EVALUATION_ERROR,
            field_id="field-quantity",
            row_id="row-1",
            run_id="synthetic-run",
            system_id="synthetic-system",
        )
        validate_exclusion_ledger(
            ledger(missing_quantity), references=(draft,)
        )

        unavailable_quantity = field(
            "field-quantity",
            ReceiptFieldName.QUANTITY,
            None,
            row_id="row-1",
            unavailable_reason="Quantity is not annotatable in this synthetic case.",
        )
        draft_with_unavailable_quantity = replace(
            draft,
            items=(replace(draft.items[0], quantity=unavailable_quantity),),
        )
        unavailable_entry = ledger_entry(
            entry_id="adjudicated-quantity-unavailable",
            category=ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
            stage=LedgerStage.REFERENCE_ANNOTATION,
            reason=LedgerReasonCode.REFERENCE_NOT_VISIBLE_OR_ANNOTATABLE,
            action=DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
            field_id="field-quantity",
            row_id="row-1",
        )
        validate_exclusion_ledger(
            ledger(unavailable_entry),
            references=(draft_with_unavailable_quantity,),
        )

    def test_available_truth_cannot_be_marked_reference_unavailable(self) -> None:
        entry = ledger_entry(
            entry_id="false-unavailability",
            category=ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
            stage=LedgerStage.REFERENCE_ANNOTATION,
            reason=LedgerReasonCode.UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE,
            action=DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
            field_id="field-unit-price",
            row_id="row-1",
        )
        with self.assertRaisesRegex(
            ExclusionLedgerValidationError, "reference-available truth"
        ):
            validate_exclusion_ledger(
                ledger(entry), references=(reference_receipt(),)
            )

    def test_external_price_missingness_does_not_change_available_truth(self) -> None:
        receipt = reference_receipt(unit_price_available=True)
        entry = ledger_entry(
            entry_id="external-price-unavailable",
            category=ExclusionCategory.OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE,
            stage=LedgerStage.EXTERNAL_REFERENCE,
            reason=LedgerReasonCode.EXTERNAL_RETAILER_REFERENCE_UNAVAILABLE,
            action=DenominatorAction.PRESERVE_OPTIONAL_MISSINGNESS,
            field_id="field-unit-price",
            row_id="row-1",
        )
        validate_exclusion_ledger(ledger(entry), references=(receipt,))
        self.assertIs(
            receipt.items[0].unit_price.availability,
            ReferenceAvailability.AVAILABLE,
        )

    def test_external_price_reason_cannot_be_reference_label_exclusion(self) -> None:
        with self.assertRaisesRegex(ValueError, "reason code"):
            ledger_entry(
                entry_id="external-price-as-truth-exclusion",
                category=ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
                stage=LedgerStage.REFERENCE_ANNOTATION,
                reason=LedgerReasonCode.EXTERNAL_RETAILER_REFERENCE_UNAVAILABLE,
                action=DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
                field_id="field-unit-price",
                row_id="row-1",
            )

    def test_unit_price_specific_reason_requires_unit_price_field(self) -> None:
        receipt = reference_receipt()
        unavailable_quantity = field(
            "field-quantity",
            ReceiptFieldName.QUANTITY,
            None,
            row_id="row-1",
            unavailable_reason="Quantity is not annotatable in this synthetic case.",
        )
        receipt = replace(
            receipt,
            items=(replace(receipt.items[0], quantity=unavailable_quantity),),
        )
        wrong_reason = ledger_entry(
            entry_id="unit-price-reason-on-quantity",
            category=ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
            stage=LedgerStage.REFERENCE_ANNOTATION,
            reason=LedgerReasonCode.UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE,
            action=DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
            field_id="field-quantity",
            row_id="row-1",
        )
        with self.assertRaisesRegex(
            ExclusionLedgerValidationError, "requires a unit-price field"
        ):
            validate_exclusion_ledger(
                ledger(wrong_reason), references=(receipt,)
            )

        generic_reason = replace(
            wrong_reason,
            ledger_entry_id="generic-reason-on-quantity",
            reason_code=LedgerReasonCode.REFERENCE_NOT_VISIBLE_OR_ANNOTATABLE,
        )
        validate_exclusion_ledger(
            ledger(generic_reason), references=(receipt,)
        )

    def test_adjudication_pending_is_not_reference_unavailable(self) -> None:
        draft = reference_receipt(status=ReferenceRecordStatus.DRAFT)
        entry = ledger_entry(
            entry_id="adjudication-pending",
            category=ExclusionCategory.ADJUDICATION_PENDING,
            stage=LedgerStage.REFERENCE_ANNOTATION,
            reason=LedgerReasonCode.ADJUDICATION_UNRESOLVED,
            action=DenominatorAction.BLOCK_AFFECTED_EVALUATION,
            field_id="field-unit-price",
            row_id="row-1",
        )
        validate_exclusion_ledger(ledger(entry), references=(draft,))

    def test_pending_entry_contradicts_finalized_reference(self) -> None:
        entry = ledger_entry(
            entry_id="invalid-pending",
            category=ExclusionCategory.ADJUDICATION_PENDING,
            stage=LedgerStage.REFERENCE_ANNOTATION,
            reason=LedgerReasonCode.ADJUDICATION_UNRESOLVED,
            action=DenominatorAction.BLOCK_AFFECTED_EVALUATION,
        )
        with self.assertRaisesRegex(ExclusionLedgerValidationError, "finalized"):
            validate_exclusion_ledger(
                ledger(entry), references=(reference_receipt(),)
            )

    def test_duplicate_ledger_entry_ids_are_rejected(self) -> None:
        entry = ledger_entry(
            entry_id="duplicate-entry",
            category=ExclusionCategory.OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE,
            stage=LedgerStage.EXTERNAL_REFERENCE,
            reason=LedgerReasonCode.EXTERNAL_RETAILER_REFERENCE_UNAVAILABLE,
            action=DenominatorAction.PRESERVE_OPTIONAL_MISSINGNESS,
        )
        with self.assertRaisesRegex(ValueError, "Duplicate exclusion-ledger"):
            ledger(entry, entry)

    def test_inconsistent_receipt_row_and_field_references_are_rejected(self) -> None:
        entry = ledger_entry(
            entry_id="bad-field-row-link",
            category=ExclusionCategory.SYSTEM_MISSING_PREDICTION,
            stage=LedgerStage.PREDICTION,
            reason=LedgerReasonCode.PREDICTION_ABSENT,
            action=DenominatorAction.INCLUDE_AS_EVALUATION_ERROR,
            field_id="field-quantity",
            row_id="another-row",
            run_id="synthetic-run",
            system_id="synthetic-system",
        )
        with self.assertRaisesRegex(ExclusionLedgerValidationError, "unknown item row"):
            validate_exclusion_ledger(
                ledger(entry), references=(reference_receipt(),)
            )

        unknown_field = replace(
            entry,
            ledger_entry_id="unknown-field-link",
            item_row_id="row-1",
            field_id="missing-field",
        )
        with self.assertRaisesRegex(ExclusionLedgerValidationError, "unknown field"):
            validate_exclusion_ledger(
                ledger(unknown_field), references=(reference_receipt(),)
            )

        unknown_receipt = replace(
            entry,
            ledger_entry_id="unknown-receipt-link",
            receipt_id="missing-receipt",
            item_row_id="row-1",
        )
        with self.assertRaisesRegex(ExclusionLedgerValidationError, "unknown receipt"):
            validate_exclusion_ledger(
                ledger(unknown_receipt), references=(reference_receipt(),)
            )

    def test_manifest_partition_conflict_is_rejected(self) -> None:
        entry = ledger_entry(
            entry_id="partition-conflict",
            category=ExclusionCategory.OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE,
            stage=LedgerStage.EXTERNAL_REFERENCE,
            reason=LedgerReasonCode.EXTERNAL_RETAILER_REFERENCE_UNAVAILABLE,
            action=DenominatorAction.PRESERVE_OPTIONAL_MISSINGNESS,
        )
        wrong_partition = replace(entry, partition_id="partition-validation")
        with self.assertRaisesRegex(ExclusionLedgerValidationError, "partition"):
            validate_exclusion_ledger(
                ledger(wrong_partition),
                manifest=manifest(),
                references=(reference_receipt(),),
            )

    def test_truth_dependent_entry_requires_reference_contract(self) -> None:
        entry = ledger_entry(
            entry_id="unverified-truth-claim",
            category=ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
            stage=LedgerStage.REFERENCE_ANNOTATION,
            reason=LedgerReasonCode.UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE,
            action=DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
            field_id="field-unit-price",
            row_id="row-1",
        )
        with self.assertRaisesRegex(ExclusionLedgerValidationError, "Task 2.5A"):
            validate_exclusion_ledger(ledger(entry))

    def test_empty_ledger_still_validates_manifest_envelope(self) -> None:
        empty = ledger()
        validate_exclusion_ledger(empty, manifest=manifest())

        tier_mismatch = ledger()
        object.__setattr__(tier_mismatch, "dataset_tier", "synthetic-other-tier")
        mismatches = (
            (replace(empty, manifest_id="another-manifest"), "manifest"),
            (replace(empty, dataset_id="another-dataset"), "dataset"),
            (tier_mismatch, "tiers conflict"),
        )
        for mismatch, message in mismatches:
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                    ExclusionLedgerValidationError, message
                ):
                    validate_exclusion_ledger(mismatch, manifest=manifest())

    def test_serialization_is_deterministic(self) -> None:
        receipt = reference_receipt()
        first_entry = ledger_entry(
            entry_id="entry-b",
            category=ExclusionCategory.OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE,
            stage=LedgerStage.EXTERNAL_REFERENCE,
            reason=LedgerReasonCode.EXTERNAL_RETAILER_REFERENCE_UNAVAILABLE,
            action=DenominatorAction.PRESERVE_OPTIONAL_MISSINGNESS,
        )
        second_entry = ledger_entry(
            entry_id="entry-a",
            category=ExclusionCategory.METRIC_NOT_ASSESSABLE,
            stage=LedgerStage.METRIC,
            reason=LedgerReasonCode.EMPTY_DENOMINATOR,
            action=DenominatorAction.REPORT_NOT_ESTIMABLE,
            receipt_id=None,
            partition_id=None,
            cohort_id=None,
        )
        item = ledger(first_entry, second_entry)
        first = serialize_exclusion_ledger(item, references=(receipt,))
        second = serialize_exclusion_ledger(item, references=(receipt,))
        payload = json.loads(first)

        self.assertEqual(first, second)
        self.assertEqual(
            ["entry-a", "entry-b"],
            [entry["ledger_entry_id"] for entry in payload["entries"]],
        )


if __name__ == "__main__":
    unittest.main()
