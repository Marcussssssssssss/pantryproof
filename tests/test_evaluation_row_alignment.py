"""Synthetic adversarial tests for row-alignment link contracts V0."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, replace

from evaluation.prediction_schema import (
    PredictionBundle,
    PredictionExecutionState,
    PredictionItemRow,
)
from evaluation.receipt_join_schema import ReceiptJoinSet
from evaluation.reference_schema import (
    ReferenceAvailability,
    ReferenceField,
    ReferenceItemRow,
    ReferenceValue,
    TierAReferenceReceipt,
)
from evaluation.row_alignment_schema import (
    PredictionReferenceRowLink,
    ReceiptRowAlignment,
    RowAlignmentExecutionStatus,
    RowAlignmentProvenance,
    RowLinkOutcome,
    serialize_row_alignment,
    serialize_row_alignment_collection,
)
from evaluation.row_alignment_validation import (
    RowAlignmentValidationError,
    validate_row_alignment,
    validate_row_alignment_collection,
)
from pipeline.contracts import ReceiptFieldName
from tests.test_evaluation_receipt_join import (
    bundle,
    join_set,
    manifest,
    prediction_receipt,
    reference_receipt,
)


def alignment_provenance(label: str = "completed") -> RowAlignmentProvenance:
    return RowAlignmentProvenance(
        event_id=f"alignment-event-{label}",
        process_version="synthetic-alignment-recorder-v0",
        source_references=(f"synthetic-alignment-source-{label}",),
        actor_reference="synthetic-alignment-actor",
    )


def reference_item_field(
    receipt_id: str,
    row_id: str,
    field_name: ReceiptFieldName,
    suffix: str,
) -> ReferenceField:
    return ReferenceField(
        field_id=f"{receipt_id}-{row_id}-{suffix}",
        receipt_id=receipt_id,
        field_name=field_name,
        availability=ReferenceAvailability.AVAILABLE,
        annotation_event_id=f"annotation-{receipt_id}",
        adjudication_event_id=f"adjudication-{receipt_id}",
        item_row_id=row_id,
        value=ReferenceValue(original_transcription=f"synthetic-{suffix}"),
    )


def reference_row(
    receipt_id: str,
    row_id: str,
    source_order: int,
) -> ReferenceItemRow:
    return ReferenceItemRow(
        row_id=row_id,
        receipt_id=receipt_id,
        source_order=source_order,
        description=reference_item_field(
            receipt_id,
            row_id,
            ReceiptFieldName.ITEM_DESCRIPTION,
            "description",
        ),
        quantity=reference_item_field(
            receipt_id, row_id, ReceiptFieldName.QUANTITY, "quantity"
        ),
        unit_price=reference_item_field(
            receipt_id, row_id, ReceiptFieldName.UNIT_PRICE, "unit-price"
        ),
        line_total=reference_item_field(
            receipt_id, row_id, ReceiptFieldName.LINE_TOTAL, "line-total"
        ),
    )


def prediction_row(
    receipt_id: str,
    row_id: str,
    output_ordinal: int,
) -> PredictionItemRow:
    return PredictionItemRow(
        runtime_row_id=row_id,
        runtime_receipt_id=receipt_id,
        output_ordinal=output_ordinal,
        fields=(),
    )


def source_context() -> tuple[
    object,
    tuple[TierAReferenceReceipt, ...],
    PredictionBundle,
    ReceiptJoinSet,
]:
    evaluation_manifest = manifest()
    reference_a = replace(
        reference_receipt("reference-a"),
        items=(
            reference_row("reference-a", "reference-row-1", 0),
            reference_row("reference-a", "reference-row-2", 1),
        ),
    )
    reference_b = replace(
        reference_receipt("reference-b"),
        items=(reference_row("reference-b", "reference-row-b", 0),),
    )
    reference_receipts = (
        reference_a,
        reference_b,
        reference_receipt("reference-c"),
        reference_receipt("reference-d"),
    )
    prediction_bundle = bundle()
    runtime_a = replace(
        prediction_bundle.receipts[0],
        rows=(
            prediction_row("runtime-a", "prediction-row-1", 9),
            prediction_row("runtime-a", "prediction-row-2", 2),
        ),
    )
    prediction_bundle = replace(
        prediction_bundle,
        receipts=(runtime_a, prediction_bundle.receipts[1]),
    )
    receipt_join = join_set(prediction_bundle=prediction_bundle)
    return evaluation_manifest, reference_receipts, prediction_bundle, receipt_join


def complete_links() -> tuple[PredictionReferenceRowLink, ...]:
    return (
        PredictionReferenceRowLink(
            row_link_id="link-matched",
            outcome=RowLinkOutcome.MATCHED,
            runtime_receipt_id="runtime-a",
            runtime_row_id="prediction-row-1",
            prediction_output_ordinal=9,
            reference_receipt_id="reference-a",
            reference_row_id="reference-row-1",
            reference_source_order=0,
            alignment_event_id="alignment-event-completed",
        ),
        PredictionReferenceRowLink(
            row_link_id="link-prediction-only",
            outcome=RowLinkOutcome.PREDICTION_ONLY,
            runtime_receipt_id="runtime-a",
            runtime_row_id="prediction-row-2",
            prediction_output_ordinal=2,
            reference_receipt_id=None,
            reference_row_id=None,
            reference_source_order=None,
            alignment_event_id="alignment-event-completed",
            unmatched_reason="Synthetic prediction row was declared unmatched.",
        ),
        PredictionReferenceRowLink(
            row_link_id="link-reference-only",
            outcome=RowLinkOutcome.REFERENCE_ONLY,
            runtime_receipt_id=None,
            runtime_row_id=None,
            prediction_output_ordinal=None,
            reference_receipt_id="reference-a",
            reference_row_id="reference-row-2",
            reference_source_order=1,
            alignment_event_id="alignment-event-completed",
            unmatched_reason="Synthetic reference row was declared unmatched.",
        ),
    )


def alignment(
    receipt_join: ReceiptJoinSet,
    *,
    join_entry_id: str = "entry-joined-a",
    execution_status: RowAlignmentExecutionStatus = (
        RowAlignmentExecutionStatus.COMPLETED
    ),
    row_links: tuple[PredictionReferenceRowLink, ...] | None = None,
    alignment_id: str = "alignment-joined-a",
    alignment_version: str = "v0",
    alignment_configuration_reference: str = "synthetic-alignment-config-v0",
) -> ReceiptRowAlignment:
    completed = execution_status is RowAlignmentExecutionStatus.COMPLETED
    return ReceiptRowAlignment(
        alignment_id=alignment_id,
        alignment_version=alignment_version,
        manifest_id=receipt_join.manifest_id,
        manifest_version=receipt_join.manifest_version,
        dataset_version=receipt_join.dataset_version,
        prediction_bundle_id=receipt_join.prediction_bundle_id,
        prediction_scope=receipt_join.prediction_scope,
        join_set_id=receipt_join.join_set_id,
        join_set_version=receipt_join.join_set_version,
        join_revision_id=receipt_join.revision_id,
        join_entry_id=join_entry_id,
        alignment_configuration_reference=alignment_configuration_reference,
        execution_status=execution_status,
        row_links=(
            (complete_links() if row_links is None else row_links)
            if completed
            else ()
        ),
        provenance=alignment_provenance(
            "completed" if completed else execution_status.value.lower()
        ),
        execution_reference="synthetic-execution-event" if completed else None,
        status_reason=(
            None
            if completed
            else f"Synthetic {execution_status.value.lower()} reason."
        ),
    )


def reference_only_alignment(
    receipt_join: ReceiptJoinSet,
    *,
    execution_status: RowAlignmentExecutionStatus = (
        RowAlignmentExecutionStatus.COMPLETED
    ),
    alignment_configuration_reference: str = "synthetic-alignment-config-v0",
) -> ReceiptRowAlignment:
    links = (
        PredictionReferenceRowLink(
            row_link_id="reference-b-only",
            outcome=RowLinkOutcome.REFERENCE_ONLY,
            runtime_receipt_id=None,
            runtime_row_id=None,
            prediction_output_ordinal=None,
            reference_receipt_id="reference-b",
            reference_row_id="reference-row-b",
            reference_source_order=0,
            alignment_event_id="alignment-event-completed",
            unmatched_reason="No prediction receipt side.",
        ),
    )
    return alignment(
        receipt_join,
        join_entry_id="entry-reference-b",
        execution_status=execution_status,
        row_links=links if execution_status is RowAlignmentExecutionStatus.COMPLETED else None,
        alignment_id="alignment-reference-b",
        alignment_configuration_reference=alignment_configuration_reference,
    )


def prediction_only_alignment(
    receipt_join: ReceiptJoinSet,
    *,
    execution_status: RowAlignmentExecutionStatus = (
        RowAlignmentExecutionStatus.COMPLETED
    ),
    alignment_configuration_reference: str = "synthetic-alignment-config-v0",
) -> ReceiptRowAlignment:
    return alignment(
        receipt_join,
        join_entry_id="entry-prediction-extra",
        execution_status=execution_status,
        row_links=(),
        alignment_id="alignment-prediction-extra",
        alignment_configuration_reference=alignment_configuration_reference,
    )


def complete_alignment_collection(
    receipt_join: ReceiptJoinSet,
) -> tuple[ReceiptRowAlignment, ...]:
    return (
        alignment(receipt_join),
        reference_only_alignment(receipt_join),
        prediction_only_alignment(receipt_join),
    )


class RowAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        (
            self.manifest,
            self.references,
            self.bundle,
            self.join_set,
        ) = source_context()

    def validate(
        self,
        item: ReceiptRowAlignment,
        *,
        join_set_value: ReceiptJoinSet | None = None,
        bundle_value: PredictionBundle | None = None,
        references_value: tuple[TierAReferenceReceipt, ...] | None = None,
    ) -> None:
        validate_row_alignment(
            item,
            join_set=join_set_value or self.join_set,
            manifest=self.manifest,
            prediction_bundle=bundle_value or self.bundle,
            reference_receipts=references_value or self.references,
        )

    def test_completed_alignment_supports_all_three_row_outcomes(self) -> None:
        item = alignment(self.join_set)
        self.validate(item)
        self.assertEqual({link.outcome for link in item.row_links}, set(RowLinkOutcome))

    def test_completed_alignment_has_exact_one_to_one_coverage(self) -> None:
        item = alignment(self.join_set)
        self.validate(item)
        self.assertEqual(
            {link.runtime_row_id for link in item.row_links if link.runtime_row_id},
            {"prediction-row-1", "prediction-row-2"},
        )
        self.assertEqual(
            {link.reference_row_id for link in item.row_links if link.reference_row_id},
            {"reference-row-1", "reference-row-2"},
        )

    def test_blocked_and_not_executed_are_separate_link_free_states(self) -> None:
        blocked = alignment(
            self.join_set, execution_status=RowAlignmentExecutionStatus.BLOCKED
        )
        not_executed = alignment(
            self.join_set,
            execution_status=RowAlignmentExecutionStatus.NOT_EXECUTED,
            alignment_id="alignment-not-executed",
        )
        self.validate(blocked)
        self.validate(not_executed)
        self.assertNotEqual(blocked.execution_status, not_executed.execution_status)
        self.assertEqual(blocked.row_links, ())
        self.assertEqual(not_executed.row_links, ())

    def test_blocked_or_unexecuted_records_cannot_contain_links(self) -> None:
        for state in (
            RowAlignmentExecutionStatus.BLOCKED,
            RowAlignmentExecutionStatus.NOT_EXECUTED,
        ):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ValueError, "must not contain row links"):
                    replace(
                        alignment(self.join_set, execution_status=state),
                        row_links=complete_links(),
                    )

    def test_blocked_or_unexecuted_records_require_reason_and_provenance(self) -> None:
        blocked = alignment(
            self.join_set, execution_status=RowAlignmentExecutionStatus.BLOCKED
        )
        with self.assertRaisesRegex(ValueError, "status_reason"):
            replace(blocked, status_reason=None)
        with self.assertRaisesRegex(TypeError, "provenance"):
            replace(blocked, provenance=None)  # type: ignore[arg-type]

    def test_completed_requires_explicit_execution_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution_reference"):
            replace(alignment(self.join_set), execution_reference=None)

    def test_duplicate_prediction_row_participation_is_rejected(self) -> None:
        links = complete_links()
        duplicate = replace(
            links[1],
            runtime_row_id="prediction-row-1",
            prediction_output_ordinal=9,
        )
        with self.assertRaisesRegex(RowAlignmentValidationError, "prediction row participates"):
            self.validate(alignment(self.join_set, row_links=(links[0], duplicate, links[2])))

    def test_duplicate_reference_row_participation_is_rejected(self) -> None:
        links = complete_links()
        duplicate = replace(
            links[2], reference_row_id="reference-row-1", reference_source_order=0
        )
        with self.assertRaisesRegex(RowAlignmentValidationError, "reference row participates"):
            self.validate(alignment(self.join_set, row_links=(links[0], links[1], duplicate)))

    def test_missing_prediction_or_reference_coverage_is_rejected(self) -> None:
        links = complete_links()
        with self.subTest("prediction"):
            with self.assertRaisesRegex(RowAlignmentValidationError, "cover prediction"):
                self.validate(alignment(self.join_set, row_links=(links[0], links[2])))
        with self.subTest("reference"):
            with self.assertRaisesRegex(RowAlignmentValidationError, "cover reference"):
                self.validate(alignment(self.join_set, row_links=(links[0], links[1])))

    def test_unknown_row_identities_are_rejected(self) -> None:
        links = complete_links()
        unknown = replace(links[0], runtime_row_id="unknown-prediction-row")
        with self.assertRaisesRegex(RowAlignmentValidationError, "unknown prediction row"):
            self.validate(alignment(self.join_set, row_links=(unknown, *links[1:])))
        unknown_reference = replace(
            links[0], reference_row_id="unknown-reference-row"
        )
        with self.assertRaisesRegex(RowAlignmentValidationError, "unknown reference row"):
            self.validate(
                alignment(
                    self.join_set,
                    row_links=(unknown_reference, *links[1:]),
                )
            )

    def test_duplicate_row_link_identity_is_rejected(self) -> None:
        links = complete_links()
        duplicate_id = replace(links[1], row_link_id="link-matched")
        with self.assertRaisesRegex(RowAlignmentValidationError, "Duplicate row-link"):
            self.validate(
                alignment(
                    self.join_set,
                    row_links=(links[0], duplicate_id, links[2]),
                )
            )

    def test_copied_audit_orders_must_equal_source_records(self) -> None:
        links = complete_links()
        bad_prediction_order = replace(links[0], prediction_output_ordinal=0)
        with self.assertRaisesRegex(RowAlignmentValidationError, "output ordinal"):
            self.validate(
                alignment(
                    self.join_set,
                    row_links=(bad_prediction_order, *links[1:]),
                )
            )
        bad_reference_order = replace(links[0], reference_source_order=9)
        with self.assertRaisesRegex(RowAlignmentValidationError, "source order"):
            self.validate(
                alignment(
                    self.join_set,
                    row_links=(bad_reference_order, *links[1:]),
                )
            )

    def test_cross_receipt_row_substitution_is_rejected(self) -> None:
        links = complete_links()
        cross_receipt = replace(
            links[2],
            reference_receipt_id="reference-b",
            reference_row_id="reference-row-b",
            reference_source_order=0,
        )
        with self.assertRaisesRegex(RowAlignmentValidationError, "another receipt"):
            self.validate(alignment(self.join_set, row_links=(links[0], links[1], cross_receipt)))

    def test_wrong_join_revision_is_rejected(self) -> None:
        item = replace(alignment(self.join_set), join_revision_id="another-revision")
        with self.assertRaisesRegex(RowAlignmentValidationError, "scope or revision"):
            self.validate(item)

    def test_wrong_prediction_bundle_or_scope_is_rejected(self) -> None:
        item = replace(alignment(self.join_set), prediction_bundle_id="other-bundle")
        with self.assertRaisesRegex(RowAlignmentValidationError, "scope or revision"):
            self.validate(item)
        other_scope = replace(
            self.join_set.prediction_scope, system_id="another-system"
        )
        with self.assertRaisesRegex(RowAlignmentValidationError, "scope or revision"):
            self.validate(replace(alignment(self.join_set), prediction_scope=other_scope))

    def test_prediction_and_reference_row_namespaces_remain_separate(self) -> None:
        reference_a = replace(
            self.references[0],
            items=(reference_row("reference-a", "same-row-id", 0),),
        )
        runtime_a = replace(
            self.bundle.receipts[0],
            rows=(prediction_row("runtime-a", "same-row-id", 4),),
        )
        bundle_value = replace(
            self.bundle, receipts=(runtime_a, self.bundle.receipts[1])
        )
        references_value = (reference_a, *self.references[1:])
        join_set_value = join_set(prediction_bundle=bundle_value)
        link = PredictionReferenceRowLink(
            row_link_id="same-text-distinct-namespaces",
            outcome=RowLinkOutcome.MATCHED,
            runtime_receipt_id="runtime-a",
            runtime_row_id="same-row-id",
            prediction_output_ordinal=4,
            reference_receipt_id="reference-a",
            reference_row_id="same-row-id",
            reference_source_order=0,
            alignment_event_id="alignment-event-completed",
        )
        item = alignment(join_set_value, row_links=(link,))
        self.validate(
            item,
            join_set_value=join_set_value,
            bundle_value=bundle_value,
            references_value=references_value,
        )
        self.assertEqual(link.runtime_row_id, link.reference_row_id)

    def test_completed_alignment_may_contain_only_unmatched_links(self) -> None:
        links = (
            *(
                PredictionReferenceRowLink(
                    row_link_id=f"unmatched-prediction-{index}",
                    outcome=RowLinkOutcome.PREDICTION_ONLY,
                    runtime_receipt_id="runtime-a",
                    runtime_row_id=row_id,
                    prediction_output_ordinal=ordinal,
                    reference_receipt_id=None,
                    reference_row_id=None,
                    reference_source_order=None,
                    alignment_event_id="alignment-event-completed",
                    unmatched_reason="Synthetic unmatched prediction row.",
                )
                for index, (row_id, ordinal) in enumerate(
                    (("prediction-row-1", 9), ("prediction-row-2", 2)), start=1
                )
            ),
            *(
                PredictionReferenceRowLink(
                    row_link_id=f"unmatched-reference-{index}",
                    outcome=RowLinkOutcome.REFERENCE_ONLY,
                    runtime_receipt_id=None,
                    runtime_row_id=None,
                    prediction_output_ordinal=None,
                    reference_receipt_id="reference-a",
                    reference_row_id=row_id,
                    reference_source_order=order,
                    alignment_event_id="alignment-event-completed",
                    unmatched_reason="Synthetic unmatched reference row.",
                )
                for index, (row_id, order) in enumerate(
                    (("reference-row-1", 0), ("reference-row-2", 1)), start=1
                )
            ),
        )
        self.validate(alignment(self.join_set, row_links=links))

    def test_zero_row_structured_output_can_complete_only_with_explicit_execution(self) -> None:
        runtime_a = replace(self.bundle.receipts[0], rows=())
        bundle_value = replace(
            self.bundle, receipts=(runtime_a, self.bundle.receipts[1])
        )
        join_set_value = join_set(prediction_bundle=bundle_value)
        links = tuple(
            PredictionReferenceRowLink(
                row_link_id=f"zero-output-{row.row_id}",
                outcome=RowLinkOutcome.REFERENCE_ONLY,
                runtime_receipt_id=None,
                runtime_row_id=None,
                prediction_output_ordinal=None,
                reference_receipt_id="reference-a",
                reference_row_id=row.row_id,
                reference_source_order=row.source_order,
                alignment_event_id="alignment-event-completed",
                unmatched_reason="Structured prediction emitted zero rows.",
            )
            for row in self.references[0].items
        )
        item = alignment(join_set_value, row_links=links)
        self.validate(item, join_set_value=join_set_value, bundle_value=bundle_value)
        self.assertIsNotNone(item.execution_reference)

    def test_fallback_does_not_imply_alignment_execution(self) -> None:
        fallback = prediction_receipt("runtime-a", fallback=True)
        bundle_value = replace(
            self.bundle, receipts=(fallback, self.bundle.receipts[1])
        )
        join_set_value = join_set(prediction_bundle=bundle_value)
        item = alignment(
            join_set_value,
            execution_status=RowAlignmentExecutionStatus.NOT_EXECUTED,
        )
        self.validate(item, join_set_value=join_set_value, bundle_value=bundle_value)
        self.assertEqual(fallback.execution_state, PredictionExecutionState.FALLBACK_NO_UPDATE)
        self.assertIsNone(item.execution_reference)

    def test_reference_only_receipt_uses_only_reference_row_links(self) -> None:
        link = PredictionReferenceRowLink(
            row_link_id="missing-prediction-reference-row",
            outcome=RowLinkOutcome.REFERENCE_ONLY,
            runtime_receipt_id=None,
            runtime_row_id=None,
            prediction_output_ordinal=None,
            reference_receipt_id="reference-b",
            reference_row_id="reference-row-b",
            reference_source_order=0,
            alignment_event_id="alignment-event-completed",
            unmatched_reason="Receipt join has no prediction receipt side.",
        )
        item = alignment(
            self.join_set,
            join_entry_id="entry-reference-b",
            row_links=(link,),
            alignment_id="alignment-reference-b",
        )
        self.validate(item)

    def test_prediction_only_receipt_uses_only_prediction_row_links(self) -> None:
        runtime_extra = replace(
            prediction_receipt("runtime-extra"),
            rows=(prediction_row("runtime-extra", "prediction-extra-row", 6),),
        )
        bundle_value = replace(
            self.bundle, receipts=(self.bundle.receipts[0], runtime_extra)
        )
        join_set_value = join_set(prediction_bundle=bundle_value)
        link = PredictionReferenceRowLink(
            row_link_id="prediction-extra-only",
            outcome=RowLinkOutcome.PREDICTION_ONLY,
            runtime_receipt_id="runtime-extra",
            runtime_row_id="prediction-extra-row",
            prediction_output_ordinal=6,
            reference_receipt_id=None,
            reference_row_id=None,
            reference_source_order=None,
            alignment_event_id="alignment-event-completed",
            unmatched_reason="Receipt join has no reference receipt side.",
        )
        item = alignment(
            join_set_value,
            join_entry_id="entry-prediction-extra",
            row_links=(link,),
            alignment_id="alignment-prediction-extra",
        )
        self.validate(
            item,
            join_set_value=join_set_value,
            bundle_value=bundle_value,
        )

    def test_post_construction_mutations_fail_closed(self) -> None:
        with self.subTest("schema"):
            item = alignment(self.join_set)
            object.__setattr__(item, "schema_version", "mutated")
            with self.assertRaisesRegex(RowAlignmentValidationError, "schema"):
                self.validate(item)
        with self.subTest("enum"):
            item = alignment(self.join_set)
            object.__setattr__(item, "execution_status", "COMPLETED")
            with self.assertRaisesRegex(RowAlignmentValidationError, "ExecutionStatus"):
                self.validate(item)
        with self.subTest("nested"):
            item = alignment(self.join_set)
            object.__setattr__(item.provenance, "source_references", ())
            with self.assertRaisesRegex(RowAlignmentValidationError, "provenance"):
                self.validate(item)

    def test_deterministic_serialization_ignores_input_link_order(self) -> None:
        first = alignment(self.join_set)
        second = replace(first, row_links=tuple(reversed(first.row_links)))
        first_json = serialize_row_alignment(
            first,
            join_set=self.join_set,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )
        second_json = serialize_row_alignment(
            second,
            join_set=self.join_set,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )
        self.assertEqual(first_json, second_json)

    def test_canonical_sort_is_not_prediction_or_reference_source_order(self) -> None:
        item = alignment(self.join_set)
        payload = json.loads(
            serialize_row_alignment(
                item,
                join_set=self.join_set,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
            )
        )
        serialized_ids = [link["row_link_id"] for link in payload["row_links"]]
        self.assertEqual(
            serialized_ids,
            ["link-matched", "link-prediction-only", "link-reference-only"],
        )
        self.assertEqual(self.bundle.receipts[0].rows[0].output_ordinal, 9)
        self.assertEqual(self.references[0].items[0].source_order, 0)

    def test_conflicting_records_for_same_complete_scope_are_rejected(self) -> None:
        first = alignment(self.join_set)
        second = replace(
            first, alignment_id="parallel-alignment", alignment_version="v1"
        )
        with self.assertRaisesRegex(RowAlignmentValidationError, "same complete scope"):
            validate_row_alignment_collection(
                (first, second),
                join_set=self.join_set,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
            )

    def test_empty_collection_is_rejected_for_nonempty_join_set(self) -> None:
        with self.assertRaisesRegex(RowAlignmentValidationError, "exactly cover"):
            validate_row_alignment_collection(
                (),
                join_set=self.join_set,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
            )

    def test_incomplete_collection_is_rejected(self) -> None:
        incomplete = complete_alignment_collection(self.join_set)[:-1]
        with self.assertRaisesRegex(RowAlignmentValidationError, "missing"):
            validate_row_alignment_collection(
                incomplete,
                join_set=self.join_set,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
            )

    def test_complete_consistent_collection_is_accepted(self) -> None:
        validate_row_alignment_collection(
            complete_alignment_collection(self.join_set),
            join_set=self.join_set,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )

    def test_complete_collection_accepts_completed_blocked_and_unexecuted(self) -> None:
        records = (
            alignment(self.join_set),
            reference_only_alignment(
                self.join_set,
                execution_status=RowAlignmentExecutionStatus.BLOCKED,
            ),
            prediction_only_alignment(
                self.join_set,
                execution_status=RowAlignmentExecutionStatus.NOT_EXECUTED,
            ),
        )
        validate_row_alignment_collection(
            records,
            join_set=self.join_set,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )
        self.assertEqual(
            {item.execution_status for item in records},
            {
                RowAlignmentExecutionStatus.COMPLETED,
                RowAlignmentExecutionStatus.BLOCKED,
                RowAlignmentExecutionStatus.NOT_EXECUTED,
            },
        )

    def test_differing_collection_configuration_references_are_rejected(self) -> None:
        records = list(complete_alignment_collection(self.join_set))
        records[2] = replace(
            records[2],
            alignment_configuration_reference="another-alignment-config",
        )
        with self.assertRaisesRegex(RowAlignmentValidationError, "inconsistent"):
            validate_row_alignment_collection(
                tuple(records),
                join_set=self.join_set,
                manifest=self.manifest,
                prediction_bundle=self.bundle,
                reference_receipts=self.references,
            )

    def test_mixed_configuration_is_rejected_for_noncompleted_records(self) -> None:
        for state in (
            RowAlignmentExecutionStatus.BLOCKED,
            RowAlignmentExecutionStatus.NOT_EXECUTED,
        ):
            with self.subTest(state=state):
                records = (
                    alignment(self.join_set),
                    reference_only_alignment(
                        self.join_set,
                        execution_status=state,
                        alignment_configuration_reference="another-config",
                    ),
                    prediction_only_alignment(self.join_set),
                )
                with self.assertRaisesRegex(
                    RowAlignmentValidationError, "inconsistent"
                ):
                    validate_row_alignment_collection(
                        records,
                        join_set=self.join_set,
                        manifest=self.manifest,
                        prediction_bundle=self.bundle,
                        reference_receipts=self.references,
                    )

    def test_individual_validation_remains_partial_development_boundary(self) -> None:
        self.validate(alignment(self.join_set))

    def test_collection_serialization_is_deterministic_across_receipts(self) -> None:
        records = complete_alignment_collection(self.join_set)
        one = serialize_row_alignment_collection(
            records,
            join_set=self.join_set,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )
        two = serialize_row_alignment_collection(
            tuple(reversed(records)),
            join_set=self.join_set,
            manifest=self.manifest,
            prediction_bundle=self.bundle,
            reference_receipts=self.references,
        )
        self.assertEqual(one, two)

    def test_records_are_frozen(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            alignment(self.join_set).alignment_id = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
