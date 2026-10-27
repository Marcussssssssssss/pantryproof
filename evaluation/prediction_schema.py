"""Immutable offline prediction-identity records for evaluation preparation.

These records preserve declared runtime output identities and states.  They do
not contain reference truth, join predictions to references, or perform line
alignment or metric computation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any

from evaluation.manifest_schema import DatasetTier, EvaluationManifest
from pipeline.contracts import (
    FieldStatus,
    OutputStage,
    ReceiptExtractionStatus,
    ReceiptFieldName,
)


PREDICTION_SCHEMA_VERSION = "0"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text.")


def _require_identifier(value: object, name: str) -> None:
    _require_text(value, name)
    assert isinstance(value, str)
    if _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f"{name} has an invalid identifier format.")


def _require_runtime_identifier(value: object, name: str) -> None:
    """Apply only the non-empty identity guarantee made by Contract V0."""

    _require_text(value, name)


def _require_tuple(value: object, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple.")


def _require_runtime_identifiers(values: tuple[str, ...], name: str) -> None:
    _require_tuple(values, name)
    for value in values:
        _require_runtime_identifier(value, f"{name} member")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates.")


def _require_schema_version(value: object) -> None:
    if value != PREDICTION_SCHEMA_VERSION:
        raise ValueError(
            f"This module implements prediction schema {PREDICTION_SCHEMA_VERSION}."
        )


class PredictionExecutionState(str, Enum):
    """Declared structural-output outcome, without redefining runtime policy."""

    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    FALLBACK_NO_UPDATE = "FALLBACK_NO_UPDATE"
    EXECUTION_FAILED = "EXECUTION_FAILED"


@dataclass(frozen=True, slots=True)
class PredictionProvenance:
    """Audit reference to the offline recording event and source artifact."""

    event_id: str
    source_record_reference: str
    recorder_version: str
    recorded_at: str | None = None
    schema_version: str = PREDICTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, "prediction provenance event_id")
        _require_text(
            self.source_record_reference,
            "prediction provenance source_record_reference",
        )
        _require_identifier(
            self.recorder_version, "prediction provenance recorder_version"
        )
        if self.recorded_at is not None:
            _require_text(self.recorded_at, "prediction provenance recorded_at")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class EvaluationRunScope:
    """Complete evaluation scope that namespaces source prediction identities."""

    dataset_id: str
    dataset_tier: DatasetTier
    partition_id: str
    cohort_id: str
    run_id: str
    system_id: str
    configuration_id: str
    output_stage: OutputStage
    schema_version: str = PREDICTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name in (
            (self.dataset_id, "dataset_id"),
            (self.partition_id, "partition_id"),
            (self.cohort_id, "cohort_id"),
            (self.run_id, "run_id"),
            (self.system_id, "system_id"),
            (self.configuration_id, "configuration_id"),
        ):
            _require_identifier(value, name)
        if not isinstance(self.dataset_tier, DatasetTier):
            raise TypeError("dataset_tier must be a DatasetTier.")
        if not isinstance(self.output_stage, OutputStage):
            raise TypeError("output_stage must be an OutputStage.")
        _require_schema_version(self.schema_version)

    @property
    def identity_key(self) -> tuple[str, ...]:
        """Return the complete immutable namespace for prediction identities."""

        return (
            self.dataset_id,
            self.dataset_tier.value,
            self.partition_id,
            self.cohort_id,
            self.run_id,
            self.system_id,
            self.configuration_id,
            self.output_stage.value,
        )


@dataclass(frozen=True, slots=True)
class PredictionField:
    """One field exactly as declared by a runtime prediction producer."""

    runtime_field_id: str
    runtime_receipt_id: str
    field_name: ReceiptFieldName
    status: FieldStatus
    item_row_id: str | None = None
    value: str | None = None
    source_token_ids: tuple[str, ...] = ()
    unresolved_reason: str | None = None
    schema_version: str = PREDICTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_runtime_identifier(self.runtime_field_id, "runtime_field_id")
        _require_runtime_identifier(self.runtime_receipt_id, "runtime_receipt_id")
        if not isinstance(self.field_name, ReceiptFieldName):
            raise TypeError("field_name must be a ReceiptFieldName.")
        if not isinstance(self.status, FieldStatus):
            raise TypeError("status must be a FieldStatus.")
        if self.item_row_id is not None:
            _require_runtime_identifier(self.item_row_id, "item_row_id")
        _require_runtime_identifiers(self.source_token_ids, "source_token_ids")

        if self.status is FieldStatus.EXTRACTED:
            _require_text(self.value, "extracted field value")
            if not self.source_token_ids:
                raise ValueError(
                    "An extracted prediction field requires source_token_ids."
                )
            if self.unresolved_reason is not None:
                raise ValueError(
                    "An extracted prediction field cannot have unresolved_reason."
                )
        else:
            if self.value is not None:
                raise ValueError(
                    "Missing or unresolved prediction fields must not contain a value."
                )
            _require_text(self.unresolved_reason, "unresolved_reason")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class PredictionItemRow:
    """One emitted runtime row with an explicit, non-semantic output ordinal."""

    runtime_row_id: str
    runtime_receipt_id: str
    output_ordinal: int
    fields: tuple[PredictionField, ...]
    schema_version: str = PREDICTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_runtime_identifier(self.runtime_row_id, "runtime_row_id")
        _require_runtime_identifier(self.runtime_receipt_id, "runtime_receipt_id")
        if isinstance(self.output_ordinal, bool) or not isinstance(
            self.output_ordinal, int
        ):
            raise TypeError("output_ordinal must be an integer.")
        if self.output_ordinal < 0:
            raise ValueError("output_ordinal must be non-negative.")
        _require_tuple(self.fields, "prediction row fields")
        if any(not isinstance(item, PredictionField) for item in self.fields):
            raise TypeError("prediction row fields contains an invalid record.")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class PredictionReceipt:
    """One runtime receipt prediction, including explicit absence of output."""

    runtime_receipt_id: str
    structured_output_present: bool
    execution_state: PredictionExecutionState
    extraction_status: ReceiptExtractionStatus | None
    receipt_fields: tuple[PredictionField, ...]
    rows: tuple[PredictionItemRow, ...]
    provenance: PredictionProvenance
    state_detail: str | None = None
    schema_version: str = PREDICTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_runtime_identifier(self.runtime_receipt_id, "runtime_receipt_id")
        if type(self.structured_output_present) is not bool:
            raise TypeError("structured_output_present must be a bool.")
        if not isinstance(self.execution_state, PredictionExecutionState):
            raise TypeError("execution_state must be a PredictionExecutionState.")
        if self.extraction_status is not None and not isinstance(
            self.extraction_status, ReceiptExtractionStatus
        ):
            raise TypeError("extraction_status must be a ReceiptExtractionStatus.")
        for value, name, expected in (
            (self.receipt_fields, "receipt_fields", PredictionField),
            (self.rows, "rows", PredictionItemRow),
        ):
            _require_tuple(value, name)
            if any(not isinstance(item, expected) for item in value):
                raise TypeError(f"{name} contains an invalid record.")
        if not isinstance(self.provenance, PredictionProvenance):
            raise TypeError("provenance must be PredictionProvenance.")

        if self.structured_output_present:
            if self.execution_state is not PredictionExecutionState.STRUCTURED_OUTPUT:
                raise ValueError(
                    "Structured output requires STRUCTURED_OUTPUT execution state."
                )
            if self.extraction_status is None:
                raise ValueError("Structured output requires extraction_status.")
            if self.state_detail is not None:
                raise ValueError(
                    "Structured output cannot contain fallback/failure state_detail."
                )
        else:
            if self.execution_state is PredictionExecutionState.STRUCTURED_OUTPUT:
                raise ValueError(
                    "Absent structured output cannot declare STRUCTURED_OUTPUT."
                )
            if self.extraction_status is not None:
                raise ValueError(
                    "Absent structured output cannot declare extraction_status."
                )
            if self.receipt_fields or self.rows:
                raise ValueError(
                    "Absent structured output cannot contain fabricated fields or rows."
                )
            _require_text(self.state_detail, "fallback/failure state_detail")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class PredictionBundle:
    """One scoped collection of offline receipt-prediction identities."""

    bundle_id: str
    scope: EvaluationRunScope
    receipts: tuple[PredictionReceipt, ...]
    provenance: PredictionProvenance
    schema_version: str = PREDICTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.bundle_id, "bundle_id")
        if not isinstance(self.scope, EvaluationRunScope):
            raise TypeError("scope must be an EvaluationRunScope.")
        _require_tuple(self.receipts, "receipts")
        if any(not isinstance(item, PredictionReceipt) for item in self.receipts):
            raise TypeError("receipts contains an invalid prediction record.")
        if not isinstance(self.provenance, PredictionProvenance):
            raise TypeError("provenance must be PredictionProvenance.")
        _require_schema_version(self.schema_version)

        from evaluation.prediction_validation import validate_prediction_bundle

        validate_prediction_bundle(self)


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _to_json_compatible(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(
        f"Unsupported prediction-contract JSON value: {type(value).__name__}."
    )


def _canonical_bundle_payload(bundle: PredictionBundle) -> dict[str, Any]:
    payload = _to_json_compatible(bundle)
    payload["receipts"] = sorted(
        payload["receipts"], key=lambda item: item["runtime_receipt_id"]
    )
    for receipt in payload["receipts"]:
        receipt["receipt_fields"] = sorted(
            receipt["receipt_fields"],
            key=lambda item: (item["field_name"], item["runtime_field_id"]),
        )
        receipt["rows"] = sorted(
            receipt["rows"],
            key=lambda item: (item["output_ordinal"], item["runtime_row_id"]),
        )
        for row in receipt["rows"]:
            row["fields"] = sorted(
                row["fields"],
                key=lambda item: (item["field_name"], item["runtime_field_id"]),
            )
    return payload


def serialize_prediction_bundle(
    bundle: PredictionBundle,
    *,
    manifest: EvaluationManifest | None = None,
) -> str:
    """Validate and serialize one bundle in canonical identity order."""

    from evaluation.prediction_validation import validate_prediction_bundle

    validate_prediction_bundle(bundle, manifest=manifest)
    return json.dumps(
        _canonical_bundle_payload(bundle),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_prediction_collection(
    bundles: tuple[PredictionBundle, ...],
    *,
    manifest: EvaluationManifest | None = None,
) -> str:
    """Validate and serialize multiple independently scoped bundles."""

    from evaluation.prediction_validation import validate_prediction_collection

    validate_prediction_collection(bundles, manifest=manifest)
    payload = [_canonical_bundle_payload(bundle) for bundle in bundles]
    payload.sort(
        key=lambda item: (
            item["scope"]["dataset_id"],
            item["scope"]["dataset_tier"],
            item["scope"]["partition_id"],
            item["scope"]["cohort_id"],
            item["scope"]["run_id"],
            item["scope"]["system_id"],
            item["scope"]["configuration_id"],
            item["scope"]["output_stage"],
            item["bundle_id"],
        )
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = (
    "PREDICTION_SCHEMA_VERSION",
    "EvaluationRunScope",
    "PredictionBundle",
    "PredictionExecutionState",
    "PredictionField",
    "PredictionItemRow",
    "PredictionProvenance",
    "PredictionReceipt",
    "serialize_prediction_bundle",
    "serialize_prediction_collection",
)
