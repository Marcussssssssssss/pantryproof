"""Structural validation for offline prediction-identity records."""

from __future__ import annotations

from evaluation.manifest_schema import EvaluationManifest
from evaluation.prediction_schema import (
    PredictionBundle,
    PredictionField,
    PredictionItemRow,
    PredictionReceipt,
)
from pipeline.contracts import ReceiptFieldName


_RECEIPT_FIELD_NAMES = {
    ReceiptFieldName.STORE_NAME,
    ReceiptFieldName.PURCHASE_DATE,
    ReceiptFieldName.RECEIPT_TOTAL,
}
_ITEM_FIELD_NAMES = {
    ReceiptFieldName.ITEM_DESCRIPTION,
    ReceiptFieldName.QUANTITY,
    ReceiptFieldName.UNIT_PRICE,
    ReceiptFieldName.LINE_TOTAL,
}


class PredictionValidationError(ValueError):
    """Raised when offline prediction identities or links are inconsistent."""


def _fail(message: str) -> None:
    raise PredictionValidationError(message)


def _validate_receipt_field(
    field: PredictionField,
    receipt: PredictionReceipt,
) -> None:
    if field.runtime_receipt_id != receipt.runtime_receipt_id:
        _fail(
            f"Prediction field {field.runtime_field_id!r} belongs to another receipt."
        )
    if field.field_name not in _RECEIPT_FIELD_NAMES:
        _fail(
            f"Item-level field {field.runtime_field_id!r} is represented at "
            "receipt level."
        )
    if field.item_row_id is not None:
        _fail(
            f"Receipt-level field {field.runtime_field_id!r} must not reference a row."
        )


def _validate_row_field(
    field: PredictionField,
    row: PredictionItemRow,
    receipt: PredictionReceipt,
) -> None:
    if field.runtime_receipt_id != receipt.runtime_receipt_id:
        _fail(
            f"Prediction field {field.runtime_field_id!r} belongs to another receipt."
        )
    if field.field_name not in _ITEM_FIELD_NAMES:
        _fail(
            f"Receipt-level field {field.runtime_field_id!r} is attached to a row."
        )
    if field.item_row_id != row.runtime_row_id:
        _fail(
            f"Prediction field {field.runtime_field_id!r} has an inconsistent row link."
        )


def _validate_receipt(receipt: PredictionReceipt) -> None:
    row_ids: set[str] = set()
    ordinals: set[int] = set()
    field_roles: dict[str, ReceiptFieldName] = {}
    receipt_roles: set[ReceiptFieldName] = set()

    for field in receipt.receipt_fields:
        _validate_receipt_field(field, receipt)
        prior_role = field_roles.get(field.runtime_field_id)
        if prior_role is not None:
            if prior_role is not field.field_name:
                _fail(
                    f"Prediction field ID {field.runtime_field_id!r} has "
                    "conflicting roles."
                )
            _fail(
                f"Duplicate prediction field ID {field.runtime_field_id!r} "
                "within receipt."
            )
        if field.field_name in receipt_roles:
            _fail(
                f"Receipt {receipt.runtime_receipt_id!r} contains duplicate "
                f"{field.field_name.value} roles."
            )
        receipt_roles.add(field.field_name)
        field_roles[field.runtime_field_id] = field.field_name

    for row in receipt.rows:
        if row.runtime_receipt_id != receipt.runtime_receipt_id:
            _fail(f"Prediction row {row.runtime_row_id!r} belongs to another receipt.")
        if row.runtime_row_id in row_ids:
            _fail(
                f"Duplicate prediction row ID {row.runtime_row_id!r} within receipt."
            )
        row_ids.add(row.runtime_row_id)
        if row.output_ordinal in ordinals:
            _fail(
                f"Duplicate prediction output ordinal {row.output_ordinal} "
                "within receipt."
            )
        ordinals.add(row.output_ordinal)

        row_roles: set[ReceiptFieldName] = set()
        for field in row.fields:
            _validate_row_field(field, row, receipt)
            if field.field_name in row_roles:
                _fail(
                    f"Prediction row {row.runtime_row_id!r} contains duplicate "
                    f"{field.field_name.value} roles."
                )
            row_roles.add(field.field_name)
            prior_role = field_roles.get(field.runtime_field_id)
            if prior_role is not None:
                if prior_role is not field.field_name:
                    _fail(
                        f"Prediction field ID {field.runtime_field_id!r} has "
                        "conflicting roles."
                    )
                _fail(
                    f"Duplicate prediction field ID {field.runtime_field_id!r} "
                    "within receipt."
                )
            field_roles[field.runtime_field_id] = field.field_name


def _validate_manifest_scope(
    bundle: PredictionBundle,
    manifest: EvaluationManifest,
) -> None:
    scope = bundle.scope
    if scope.dataset_id != manifest.dataset_id:
        _fail("Prediction scope refers to another manifest dataset.")
    if scope.dataset_tier is not manifest.dataset_tier:
        _fail("Prediction scope and manifest dataset tiers conflict.")
    if scope.partition_id not in {
        partition.partition_id for partition in manifest.partitions
    }:
        _fail("Prediction scope references an unknown manifest partition.")
    if scope.cohort_id not in {cohort.cohort_id for cohort in manifest.cohorts}:
        _fail("Prediction scope references an unknown manifest cohort.")


def validate_prediction_bundle(
    bundle: PredictionBundle,
    *,
    manifest: EvaluationManifest | None = None,
) -> None:
    """Validate prediction identities without reference joins or correctness."""

    if not isinstance(bundle, PredictionBundle):
        raise TypeError("bundle must be a PredictionBundle.")
    if manifest is not None:
        if not isinstance(manifest, EvaluationManifest):
            raise TypeError("manifest must be an EvaluationManifest.")
        _validate_manifest_scope(bundle, manifest)

    receipt_ids: set[str] = set()
    for receipt in bundle.receipts:
        if receipt.runtime_receipt_id in receipt_ids:
            _fail(
                "Duplicate prediction receipt key within one evaluation scope: "
                f"{receipt.runtime_receipt_id!r}."
            )
        receipt_ids.add(receipt.runtime_receipt_id)
        _validate_receipt(receipt)


def validate_prediction_collection(
    bundles: tuple[PredictionBundle, ...],
    *,
    manifest: EvaluationManifest | None = None,
) -> None:
    """Validate complete keys across independently scoped prediction bundles."""

    if not isinstance(bundles, tuple):
        raise TypeError("bundles must be a tuple.")
    if any(not isinstance(bundle, PredictionBundle) for bundle in bundles):
        raise TypeError("bundles contains an invalid prediction bundle.")

    bundle_ids: set[str] = set()
    complete_receipt_keys: set[tuple[str, ...]] = set()
    for bundle in bundles:
        if bundle.bundle_id in bundle_ids:
            _fail(f"Duplicate prediction bundle ID {bundle.bundle_id!r}.")
        bundle_ids.add(bundle.bundle_id)
        validate_prediction_bundle(bundle, manifest=manifest)
        for receipt in bundle.receipts:
            key = (*bundle.scope.identity_key, receipt.runtime_receipt_id)
            if key in complete_receipt_keys:
                _fail("Duplicate complete prediction receipt key across bundles.")
            complete_receipt_keys.add(key)


__all__ = (
    "PredictionValidationError",
    "validate_prediction_bundle",
    "validate_prediction_collection",
)
