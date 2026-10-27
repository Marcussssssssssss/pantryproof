"""Synthetic tests for offline prediction-identity contracts V0."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, fields, replace

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
    PREDICTION_SCHEMA_VERSION,
    EvaluationRunScope,
    PredictionBundle,
    PredictionExecutionState,
    PredictionField,
    PredictionItemRow,
    PredictionProvenance,
    PredictionReceipt,
    serialize_prediction_bundle,
    serialize_prediction_collection,
)
from evaluation.prediction_validation import (
    PredictionValidationError,
    validate_prediction_bundle,
    validate_prediction_collection,
)
from pipeline.contracts import (
    FieldStatus,
    OutputStage,
    ReceiptExtractionStatus,
    ReceiptFieldName,
)


RUNTIME_RECEIPT_ID = "runtime-receipt-alpha"
RUNTIME_ROW_ID = "runtime-receipt-alpha:b2:row:000000"


def provenance(label: str) -> PredictionProvenance:
    return PredictionProvenance(
        event_id="synthetic-prediction-event",
        source_record_reference=f"memory://synthetic/{label}",
        recorder_version="synthetic-recorder-v0",
    )


def scope(
    *,
    system_id: str = "B2-layout-graph-v0",
    configuration_id: str = "synthetic-b2-configuration",
    run_id: str = "synthetic-run",
    partition_id: str = "partition-training",
    cohort_id: str = "cohort-primary",
) -> EvaluationRunScope:
    return EvaluationRunScope(
        dataset_id="synthetic-tier-a",
        dataset_tier=DatasetTier.TIER_A,
        partition_id=partition_id,
        cohort_id=cohort_id,
        run_id=run_id,
        system_id=system_id,
        configuration_id=configuration_id,
        output_stage=OutputStage.PRE_REVIEW_AUTOMATIC,
    )


def prediction_field(
    runtime_field_id: str,
    field_name: ReceiptFieldName,
    status: FieldStatus,
    *,
    runtime_receipt_id: str = RUNTIME_RECEIPT_ID,
    row_id: str | None = None,
    value: str | None = None,
    source_token_ids: tuple[str, ...] = (),
    reason: str | None = None,
) -> PredictionField:
    return PredictionField(
        runtime_field_id=runtime_field_id,
        runtime_receipt_id=runtime_receipt_id,
        field_name=field_name,
        status=status,
        item_row_id=row_id,
        value=value,
        source_token_ids=source_token_ids,
        unresolved_reason=reason,
    )


def item_fields(
    *,
    runtime_receipt_id: str = RUNTIME_RECEIPT_ID,
    row_id: str = RUNTIME_ROW_ID,
) -> tuple[PredictionField, ...]:
    return (
        prediction_field(
            f"{row_id}:item-description",
            ReceiptFieldName.ITEM_DESCRIPTION,
            FieldStatus.EXTRACTED,
            runtime_receipt_id=runtime_receipt_id,
            row_id=row_id,
            value="Synthetic Milk 1L",
            source_token_ids=(f"{runtime_receipt_id}:token:1",),
        ),
        prediction_field(
            f"{row_id}:quantity",
            ReceiptFieldName.QUANTITY,
            FieldStatus.MISSING,
            runtime_receipt_id=runtime_receipt_id,
            row_id=row_id,
            reason="Synthetic producer emitted a missing quantity field.",
        ),
        prediction_field(
            f"{row_id}:unit-price",
            ReceiptFieldName.UNIT_PRICE,
            FieldStatus.UNRESOLVED,
            runtime_receipt_id=runtime_receipt_id,
            row_id=row_id,
            source_token_ids=(f"{runtime_receipt_id}:token:2",),
            reason="Synthetic producer retained ambiguous price evidence.",
        ),
        prediction_field(
            f"{row_id}:line-total",
            ReceiptFieldName.LINE_TOTAL,
            FieldStatus.EXTRACTED,
            runtime_receipt_id=runtime_receipt_id,
            row_id=row_id,
            value="6.50",
            source_token_ids=(f"{runtime_receipt_id}:token:3",),
        ),
    )


def structured_receipt(
    *,
    runtime_receipt_id: str = RUNTIME_RECEIPT_ID,
    row_id: str = RUNTIME_ROW_ID,
) -> PredictionReceipt:
    return PredictionReceipt(
        runtime_receipt_id=runtime_receipt_id,
        structured_output_present=True,
        execution_state=PredictionExecutionState.STRUCTURED_OUTPUT,
        extraction_status=ReceiptExtractionStatus.PARTIAL,
        receipt_fields=(
            prediction_field(
                f"{runtime_receipt_id}:b2:store-name",
                ReceiptFieldName.STORE_NAME,
                FieldStatus.EXTRACTED,
                runtime_receipt_id=runtime_receipt_id,
                value="Synthetic Grocer",
                source_token_ids=(f"{runtime_receipt_id}:token:0",),
            ),
            prediction_field(
                f"{runtime_receipt_id}:b2:purchase-date",
                ReceiptFieldName.PURCHASE_DATE,
                FieldStatus.MISSING,
                runtime_receipt_id=runtime_receipt_id,
                reason="Synthetic producer emitted a missing date field.",
            ),
        ),
        rows=(
            PredictionItemRow(
                runtime_row_id=row_id,
                runtime_receipt_id=runtime_receipt_id,
                output_ordinal=0,
                fields=item_fields(
                    runtime_receipt_id=runtime_receipt_id,
                    row_id=row_id,
                ),
            ),
        ),
        provenance=provenance(runtime_receipt_id),
    )


def fallback_receipt(
    runtime_receipt_id: str = "runtime-receipt-fallback",
) -> PredictionReceipt:
    return PredictionReceipt(
        runtime_receipt_id=runtime_receipt_id,
        structured_output_present=False,
        execution_state=PredictionExecutionState.FALLBACK_NO_UPDATE,
        extraction_status=None,
        receipt_fields=(),
        rows=(),
        state_detail="Synthetic recorded insufficient-source fallback.",
        provenance=provenance(runtime_receipt_id),
    )


def bundle(
    *,
    bundle_id: str = "synthetic-prediction-bundle",
    run_scope: EvaluationRunScope | None = None,
    receipts: tuple[PredictionReceipt, ...] | None = None,
) -> PredictionBundle:
    return PredictionBundle(
        bundle_id=bundle_id,
        scope=run_scope or scope(),
        receipts=receipts if receipts is not None else (structured_receipt(),),
        provenance=provenance(bundle_id),
    )


def manifest() -> EvaluationManifest:
    reference_receipt_id = "reference-receipt-different-namespace"
    return EvaluationManifest(
        manifest_id="synthetic-manifest",
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
                reference_receipt_id,
                "partition-training",
                "synthetic-membership",
            ),
        ),
        related_groups=(
            RelatedRecordGroup(
                "transaction-reference-receipt",
                RelatedGroupKind.TRANSACTION,
                (reference_receipt_id,),
                "synthetic-transaction-group",
            ),
            RelatedRecordGroup(
                "contributor-reference-receipt",
                RelatedGroupKind.CONTRIBUTOR,
                (reference_receipt_id,),
                "synthetic-contributor-group",
            ),
        ),
        cohorts=(
            CohortDefinition(
                "cohort-primary",
                CohortKind.PRIMARY_TIER_A,
                "synthetic-tier-a",
                (reference_receipt_id,),
                "synthetic-primary-cohort",
            ),
            CohortDefinition(
                "cohort-unseen-retailer",
                CohortKind.UNSEEN_RETAILER,
                "synthetic-tier-a",
                (),
                "synthetic-unseen-cohort",
            ),
            CohortDefinition(
                "cohort-branch-generalization",
                CohortKind.BRANCH_GENERALIZATION,
                "synthetic-tier-a",
                (),
                "synthetic-branch-cohort",
            ),
        ),
        provenance=AuditProvenance(
            event_id="synthetic-manifest-event",
            source_reference="synthetic-manifest-source",
            process_version="synthetic-manifest-process-v0",
        ),
    )


class PredictionIdentityTests(unittest.TestCase):
    def test_valid_bundle_preserves_scope_rows_fields_and_states(self) -> None:
        item = bundle(receipts=(structured_receipt(), fallback_receipt()))

        validate_prediction_bundle(item)
        self.assertEqual(PREDICTION_SCHEMA_VERSION, item.schema_version)
        self.assertEqual(RUNTIME_ROW_ID, item.receipts[0].rows[0].runtime_row_id)
        self.assertIs(
            FieldStatus.MISSING,
            item.receipts[0].rows[0].fields[1].status,
        )
        self.assertFalse(item.receipts[1].structured_output_present)

    def test_records_are_frozen_and_slotted(self) -> None:
        item = bundle()
        with self.assertRaises(FrozenInstanceError):
            item.bundle_id = "changed"  # type: ignore[misc]
        self.assertFalse(hasattr(item, "__dict__"))

    def test_b2_and_b3_may_reuse_source_ids_under_different_scopes(self) -> None:
        b2 = bundle(bundle_id="bundle-b2")
        b3 = bundle(
            bundle_id="bundle-b3",
            run_scope=scope(
                system_id="B3-generic-rules-v0",
                configuration_id="synthetic-b3-configuration",
            ),
        )

        validate_prediction_collection((b2, b3))
        self.assertEqual(
            b2.receipts[0].rows[0].fields[0].runtime_field_id,
            b3.receipts[0].rows[0].fields[0].runtime_field_id,
        )
        self.assertNotEqual(b2.scope.identity_key, b3.scope.identity_key)

    def test_source_ids_may_repeat_across_run_configuration_and_stage(self) -> None:
        base = bundle(bundle_id="bundle-base")
        variants = (
            bundle(
                bundle_id="bundle-other-run",
                run_scope=replace(base.scope, run_id="another-run"),
            ),
            bundle(
                bundle_id="bundle-other-configuration",
                run_scope=replace(
                    base.scope, configuration_id="another-configuration"
                ),
            ),
            bundle(
                bundle_id="bundle-other-stage",
                run_scope=replace(
                    base.scope, output_stage=OutputStage.HUMAN_REVIEWED
                ),
            ),
        )
        validate_prediction_collection((base, *variants))

    def test_duplicate_complete_receipt_key_across_bundles_is_rejected(self) -> None:
        first = bundle(bundle_id="bundle-first")
        second = bundle(bundle_id="bundle-second")
        with self.assertRaisesRegex(
            PredictionValidationError, "complete prediction receipt key"
        ):
            validate_prediction_collection((first, second))

    def test_duplicate_receipt_key_within_scope_is_rejected(self) -> None:
        receipt = structured_receipt()
        with self.assertRaisesRegex(
            PredictionValidationError, "Duplicate prediction receipt key"
        ):
            bundle(receipts=(receipt, receipt))

    def test_duplicate_row_identity_is_rejected(self) -> None:
        receipt = structured_receipt()
        invalid = replace(receipt, rows=(receipt.rows[0], receipt.rows[0]))
        with self.assertRaisesRegex(PredictionValidationError, "Duplicate prediction row"):
            bundle(receipts=(invalid,))

    def test_duplicate_output_ordinal_is_rejected(self) -> None:
        receipt = structured_receipt()
        second_row_id = f"{RUNTIME_RECEIPT_ID}:b2:row:000001"
        second = PredictionItemRow(
            runtime_row_id=second_row_id,
            runtime_receipt_id=RUNTIME_RECEIPT_ID,
            output_ordinal=0,
            fields=item_fields(row_id=second_row_id),
        )
        invalid = replace(receipt, rows=(*receipt.rows, second))
        with self.assertRaisesRegex(PredictionValidationError, "output ordinal"):
            bundle(receipts=(invalid,))

    def test_duplicate_field_identity_is_rejected(self) -> None:
        receipt = structured_receipt()
        duplicate = replace(
            receipt.rows[0].fields[0],
            runtime_field_id=receipt.receipt_fields[0].runtime_field_id,
        )
        invalid_row = replace(
            receipt.rows[0], fields=(duplicate, *receipt.rows[0].fields[1:])
        )
        invalid = replace(receipt, rows=(invalid_row,))
        with self.assertRaisesRegex(PredictionValidationError, "field ID"):
            bundle(receipts=(invalid,))

    def test_duplicate_field_role_is_rejected(self) -> None:
        receipt = structured_receipt()
        duplicate_role = replace(
            receipt.receipt_fields[0], runtime_field_id="another-store-field"
        )
        invalid = replace(
            receipt,
            receipt_fields=(*receipt.receipt_fields, duplicate_role),
        )
        with self.assertRaisesRegex(PredictionValidationError, "duplicate STORE_NAME"):
            bundle(receipts=(invalid,))

    def test_row_linked_to_another_receipt_is_rejected(self) -> None:
        receipt = structured_receipt()
        wrong_row = replace(
            receipt.rows[0], runtime_receipt_id="another-runtime-receipt"
        )
        with self.assertRaisesRegex(PredictionValidationError, "another receipt"):
            bundle(receipts=(replace(receipt, rows=(wrong_row,)),))

    def test_field_linked_to_another_receipt_is_rejected(self) -> None:
        receipt = structured_receipt()
        wrong_field = replace(
            receipt.rows[0].fields[0],
            runtime_receipt_id="another-runtime-receipt",
        )
        wrong_row = replace(
            receipt.rows[0], fields=(wrong_field, *receipt.rows[0].fields[1:])
        )
        with self.assertRaisesRegex(PredictionValidationError, "another receipt"):
            bundle(receipts=(replace(receipt, rows=(wrong_row,)),))

    def test_field_linked_to_another_row_is_rejected(self) -> None:
        receipt = structured_receipt()
        wrong_field = replace(
            receipt.rows[0].fields[0], item_row_id="another-runtime-row"
        )
        wrong_row = replace(
            receipt.rows[0], fields=(wrong_field, *receipt.rows[0].fields[1:])
        )
        with self.assertRaisesRegex(PredictionValidationError, "row link"):
            bundle(receipts=(replace(receipt, rows=(wrong_row,)),))

    def test_receipt_and_item_field_roles_cannot_cross_scopes(self) -> None:
        receipt = structured_receipt()
        item_at_receipt = replace(
            receipt.rows[0].fields[0], item_row_id=None
        )
        with self.assertRaisesRegex(PredictionValidationError, "Item-level field"):
            bundle(receipts=(replace(receipt, receipt_fields=(item_at_receipt,)),))

        receipt_at_row = replace(
            receipt.receipt_fields[0], item_row_id=RUNTIME_ROW_ID
        )
        invalid_row = replace(receipt.rows[0], fields=(receipt_at_row,))
        with self.assertRaisesRegex(PredictionValidationError, "Receipt-level field"):
            bundle(receipts=(replace(receipt, rows=(invalid_row,)),))

    def test_invalid_offline_and_runtime_identifiers_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "dataset_id"):
            replace(scope(), dataset_id="not available")

        with self.assertRaisesRegex(ValueError, "runtime_field_id"):
            prediction_field(
                " ",
                ReceiptFieldName.STORE_NAME,
                FieldStatus.MISSING,
                reason="Synthetic missing field.",
            )

    def test_non_ascii_runtime_identifiers_are_preserved(self) -> None:
        runtime_id = "收据 α"
        row_id = "行 α"
        receipt = structured_receipt(
            runtime_receipt_id=runtime_id,
            row_id=row_id,
        )
        item = bundle(receipts=(receipt,))
        validate_prediction_bundle(item)
        self.assertEqual(runtime_id, item.receipts[0].runtime_receipt_id)

    def test_missing_and_unresolved_fields_preserve_null_values(self) -> None:
        payload = json.loads(serialize_prediction_bundle(bundle()))
        row_fields = payload["receipts"][0]["rows"][0]["fields"]
        by_role = {item["field_name"]: item for item in row_fields}

        self.assertIsNone(by_role["QUANTITY"]["value"])
        self.assertEqual("MISSING", by_role["QUANTITY"]["status"])
        self.assertIsNone(by_role["UNIT_PRICE"]["value"])
        self.assertEqual("UNRESOLVED", by_role["UNIT_PRICE"]["status"])

    def test_extracted_and_non_extracted_value_invariants_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            prediction_field(
                "empty-extracted",
                ReceiptFieldName.STORE_NAME,
                FieldStatus.EXTRACTED,
            )
        with self.assertRaisesRegex(ValueError, "must not contain a value"):
            prediction_field(
                "populated-missing",
                ReceiptFieldName.STORE_NAME,
                FieldStatus.MISSING,
                value="fabricated",
                reason="Synthetic missing field.",
            )

        with self.assertRaisesRegex(ValueError, "requires source_token_ids"):
            prediction_field(
                "extracted-without-source",
                ReceiptFieldName.STORE_NAME,
                FieldStatus.EXTRACTED,
                value="Synthetic value",
            )

    def test_valid_fallback_and_execution_failure_have_no_structured_content(self) -> None:
        failure = PredictionReceipt(
            runtime_receipt_id="runtime-receipt-failure",
            structured_output_present=False,
            execution_state=PredictionExecutionState.EXECUTION_FAILED,
            extraction_status=None,
            receipt_fields=(),
            rows=(),
            state_detail="Synthetic execution failure.",
            provenance=provenance("runtime-receipt-failure"),
        )
        validate_prediction_bundle(bundle(receipts=(fallback_receipt(), failure)))

    def test_absent_structured_output_cannot_contain_fields_or_rows(self) -> None:
        structured = structured_receipt()
        with self.assertRaisesRegex(ValueError, "fabricated fields or rows"):
            PredictionReceipt(
                runtime_receipt_id=RUNTIME_RECEIPT_ID,
                structured_output_present=False,
                execution_state=PredictionExecutionState.FALLBACK_NO_UPDATE,
                extraction_status=None,
                receipt_fields=structured.receipt_fields,
                rows=(),
                state_detail="Synthetic invalid fallback.",
                provenance=provenance("invalid-fallback"),
            )

    def test_structured_output_state_and_status_must_be_consistent(self) -> None:
        base = structured_receipt()
        with self.assertRaisesRegex(ValueError, "STRUCTURED_OUTPUT execution state"):
            replace(
                base,
                execution_state=PredictionExecutionState.FALLBACK_NO_UPDATE,
            )
        with self.assertRaisesRegex(ValueError, "requires extraction_status"):
            replace(base, extraction_status=None)

    def test_output_ordinal_is_explicit_and_not_parsed_from_row_id(self) -> None:
        row = PredictionItemRow(
            runtime_row_id="opaque-row-without-an-ordinal",
            runtime_receipt_id=RUNTIME_RECEIPT_ID,
            output_ordinal=7,
            fields=(),
        )
        receipt = replace(structured_receipt(), rows=(row,))
        item = bundle(receipts=(receipt,))
        self.assertEqual(7, item.receipts[0].rows[0].output_ordinal)

        with self.assertRaisesRegex(TypeError, "output_ordinal"):
            replace(row, output_ordinal=True)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            replace(row, output_ordinal=-1)

    def test_manifest_scope_validation_does_not_assume_receipt_id_equality(self) -> None:
        item = bundle()
        dataset_manifest = manifest()

        validate_prediction_bundle(item, manifest=dataset_manifest)
        self.assertNotEqual(
            item.receipts[0].runtime_receipt_id,
            dataset_manifest.receipts[0].receipt_id,
        )

    def test_manifest_dataset_partition_and_cohort_mismatches_are_rejected(self) -> None:
        dataset_manifest = manifest()
        cases = (
            (
                replace(bundle().scope, dataset_id="another-dataset"),
                "another manifest dataset",
            ),
            (
                replace(bundle().scope, partition_id="missing-partition"),
                "unknown manifest partition",
            ),
            (
                replace(bundle().scope, cohort_id="missing-cohort"),
                "unknown manifest cohort",
            ),
        )
        for invalid_scope, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(PredictionValidationError, message):
                    validate_prediction_bundle(
                        bundle(
                            bundle_id=f"bundle-{invalid_scope.partition_id}",
                            run_scope=invalid_scope,
                        ),
                        manifest=dataset_manifest,
                    )

    def test_serialization_preserves_absent_fields_and_no_output_distinction(self) -> None:
        receipt = structured_receipt()
        receipt = replace(receipt, receipt_fields=(receipt.receipt_fields[0],))
        item = bundle(receipts=(receipt, fallback_receipt()))
        payload = json.loads(serialize_prediction_bundle(item))
        by_receipt = {value["runtime_receipt_id"]: value for value in payload["receipts"]}

        structured = by_receipt[RUNTIME_RECEIPT_ID]
        fallback = by_receipt["runtime-receipt-fallback"]
        self.assertEqual(1, len(structured["receipt_fields"]))
        self.assertNotIn(
            "PURCHASE_DATE",
            {field["field_name"] for field in structured["receipt_fields"]},
        )
        self.assertTrue(structured["structured_output_present"])
        self.assertFalse(fallback["structured_output_present"])
        self.assertEqual([], fallback["receipt_fields"])
        self.assertEqual([], fallback["rows"])

    def test_serialization_is_canonical_and_preserves_nulls(self) -> None:
        first_receipt = structured_receipt()
        second_receipt = fallback_receipt()
        first = bundle(receipts=(first_receipt, second_receipt))
        reversed_fields = tuple(reversed(first_receipt.receipt_fields))
        reversed_row_fields = tuple(reversed(first_receipt.rows[0].fields))
        reordered_first = replace(
            first_receipt,
            receipt_fields=reversed_fields,
            rows=(replace(first_receipt.rows[0], fields=reversed_row_fields),),
        )
        second = bundle(receipts=(second_receipt, reordered_first))

        self.assertEqual(
            serialize_prediction_bundle(first),
            serialize_prediction_bundle(second),
        )
        self.assertIn('"extraction_status":null', serialize_prediction_bundle(first))

    def test_collection_serialization_is_canonical_by_complete_scope(self) -> None:
        b2 = bundle(bundle_id="bundle-b2")
        b3 = bundle(
            bundle_id="bundle-b3",
            run_scope=scope(
                system_id="B3-generic-rules-v0",
                configuration_id="synthetic-b3-configuration",
            ),
        )
        self.assertEqual(
            serialize_prediction_collection((b2, b3)),
            serialize_prediction_collection((b3, b2)),
        )

    def test_no_reference_truth_or_join_identity_is_present(self) -> None:
        public_fields = {
            item.name
            for record in (
                EvaluationRunScope,
                PredictionField,
                PredictionItemRow,
                PredictionReceipt,
                PredictionBundle,
            )
            for item in fields(record)
        }
        self.assertNotIn("reference_receipt_id", public_fields)
        self.assertNotIn("reference_value", public_fields)
        self.assertNotIn("correct", public_fields)

    def test_unsupported_schema_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "prediction schema"):
            replace(scope(), schema_version="future")


if __name__ == "__main__":
    unittest.main()
