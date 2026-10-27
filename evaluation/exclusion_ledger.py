"""Typed offline exclusion/reason ledger for provisional Tier A evaluation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from evaluation.manifest_schema import AuditProvenance, DatasetTier, EvaluationManifest
from evaluation.reference_schema import (
    ReferenceAvailability,
    ReferenceRecordStatus,
    TierAReferenceReceipt,
    to_json_compatible,
)
from pipeline.contracts import ReceiptFieldName


EXCLUSION_LEDGER_SCHEMA_VERSION = "0"
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


class LedgerStage(str, Enum):
    DATASET_ELIGIBILITY = "DATASET_ELIGIBILITY"
    REFERENCE_ANNOTATION = "REFERENCE_ANNOTATION"
    PREDICTION = "PREDICTION"
    SYSTEM_EXECUTION = "SYSTEM_EXECUTION"
    REVIEW_RESOLUTION = "REVIEW_RESOLUTION"
    CALIBRATION = "CALIBRATION"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"
    METRIC = "METRIC"
    CONFIGURATION_FREEZE = "CONFIGURATION_FREEZE"


class ExclusionCategory(str, Enum):
    DATASET_LEVEL_EXCLUSION = "DATASET_LEVEL_EXCLUSION"
    REFERENCE_LABEL_UNAVAILABLE = "REFERENCE_LABEL_UNAVAILABLE"
    ADJUDICATION_PENDING = "ADJUDICATION_PENDING"
    SYSTEM_MISSING_PREDICTION = "SYSTEM_MISSING_PREDICTION"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"
    REVIEW_WITHOUT_RESOLUTION = "REVIEW_WITHOUT_RESOLUTION"
    CALIBRATION_OR_PROBABILITY_UNAVAILABLE = (
        "CALIBRATION_OR_PROBABILITY_UNAVAILABLE"
    )
    OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE = (
        "OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE"
    )
    METRIC_NOT_ASSESSABLE = "METRIC_NOT_ASSESSABLE"
    CONFIGURATION_OR_FREEZE_FAILURE = "CONFIGURATION_OR_FREEZE_FAILURE"


class LedgerReasonCode(str, Enum):
    DATASET_INELIGIBLE = "DATASET_INELIGIBLE"
    REFERENCE_NOT_VISIBLE_OR_ANNOTATABLE = (
        "REFERENCE_NOT_VISIBLE_OR_ANNOTATABLE"
    )
    UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE = (
        "UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE"
    )
    ADJUDICATION_UNRESOLVED = "ADJUDICATION_UNRESOLVED"
    PREDICTION_ABSENT = "PREDICTION_ABSENT"
    PRE_RESOLUTION_FAILURE = "PRE_RESOLUTION_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    REVIEW_RESOLUTION_ABSENT = "REVIEW_RESOLUTION_ABSENT"
    PROBABILITY_UNAVAILABLE = "PROBABILITY_UNAVAILABLE"
    CALIBRATION_UNAVAILABLE = "CALIBRATION_UNAVAILABLE"
    EXTERNAL_RETAILER_REFERENCE_UNAVAILABLE = (
        "EXTERNAL_RETAILER_REFERENCE_UNAVAILABLE"
    )
    EMPTY_DENOMINATOR = "EMPTY_DENOMINATOR"
    MANDATORY_EVIDENCE_UNAVAILABLE = "MANDATORY_EVIDENCE_UNAVAILABLE"
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    FREEZE_EVIDENCE_MISSING = "FREEZE_EVIDENCE_MISSING"
    PARTITION_CONTROL_FAILURE = "PARTITION_CONTROL_FAILURE"


class DenominatorAction(str, Enum):
    EXCLUDE_FROM_DATASET = "EXCLUDE_FROM_DATASET"
    EXCLUDE_TRUTH_DEPENDENT_FIELD = "EXCLUDE_TRUTH_DEPENDENT_FIELD"
    BLOCK_AFFECTED_EVALUATION = "BLOCK_AFFECTED_EVALUATION"
    INCLUDE_AS_EVALUATION_ERROR = "INCLUDE_AS_EVALUATION_ERROR"
    RETAIN_IN_APPLICABLE_DENOMINATORS = "RETAIN_IN_APPLICABLE_DENOMINATORS"
    PRESERVE_OPTIONAL_MISSINGNESS = "PRESERVE_OPTIONAL_MISSINGNESS"
    REPORT_NOT_ESTIMABLE = "REPORT_NOT_ESTIMABLE"
    BLOCK_RUN_OR_METRIC = "BLOCK_RUN_OR_METRIC"


_EXPECTED_STAGE = {
    ExclusionCategory.DATASET_LEVEL_EXCLUSION: LedgerStage.DATASET_ELIGIBILITY,
    ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE: LedgerStage.REFERENCE_ANNOTATION,
    ExclusionCategory.ADJUDICATION_PENDING: LedgerStage.REFERENCE_ANNOTATION,
    ExclusionCategory.SYSTEM_MISSING_PREDICTION: LedgerStage.PREDICTION,
    ExclusionCategory.SYSTEM_FAILURE: LedgerStage.SYSTEM_EXECUTION,
    ExclusionCategory.REVIEW_WITHOUT_RESOLUTION: LedgerStage.REVIEW_RESOLUTION,
    ExclusionCategory.CALIBRATION_OR_PROBABILITY_UNAVAILABLE: LedgerStage.CALIBRATION,
    ExclusionCategory.OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE: LedgerStage.EXTERNAL_REFERENCE,
    ExclusionCategory.METRIC_NOT_ASSESSABLE: LedgerStage.METRIC,
    ExclusionCategory.CONFIGURATION_OR_FREEZE_FAILURE: LedgerStage.CONFIGURATION_FREEZE,
}

_EXPECTED_ACTION = {
    ExclusionCategory.DATASET_LEVEL_EXCLUSION: DenominatorAction.EXCLUDE_FROM_DATASET,
    ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE: DenominatorAction.EXCLUDE_TRUTH_DEPENDENT_FIELD,
    ExclusionCategory.ADJUDICATION_PENDING: DenominatorAction.BLOCK_AFFECTED_EVALUATION,
    ExclusionCategory.SYSTEM_MISSING_PREDICTION: DenominatorAction.INCLUDE_AS_EVALUATION_ERROR,
    ExclusionCategory.SYSTEM_FAILURE: DenominatorAction.RETAIN_IN_APPLICABLE_DENOMINATORS,
    ExclusionCategory.REVIEW_WITHOUT_RESOLUTION: DenominatorAction.RETAIN_IN_APPLICABLE_DENOMINATORS,
    ExclusionCategory.CALIBRATION_OR_PROBABILITY_UNAVAILABLE: DenominatorAction.RETAIN_IN_APPLICABLE_DENOMINATORS,
    ExclusionCategory.OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE: DenominatorAction.PRESERVE_OPTIONAL_MISSINGNESS,
    ExclusionCategory.METRIC_NOT_ASSESSABLE: DenominatorAction.REPORT_NOT_ESTIMABLE,
    ExclusionCategory.CONFIGURATION_OR_FREEZE_FAILURE: DenominatorAction.BLOCK_RUN_OR_METRIC,
}

_ALLOWED_REASONS = {
    ExclusionCategory.DATASET_LEVEL_EXCLUSION: {
        LedgerReasonCode.DATASET_INELIGIBLE,
    },
    ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE: {
        LedgerReasonCode.REFERENCE_NOT_VISIBLE_OR_ANNOTATABLE,
        LedgerReasonCode.UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE,
    },
    ExclusionCategory.ADJUDICATION_PENDING: {
        LedgerReasonCode.ADJUDICATION_UNRESOLVED,
    },
    ExclusionCategory.SYSTEM_MISSING_PREDICTION: {
        LedgerReasonCode.PREDICTION_ABSENT,
    },
    ExclusionCategory.SYSTEM_FAILURE: {
        LedgerReasonCode.PRE_RESOLUTION_FAILURE,
        LedgerReasonCode.EXECUTION_FAILURE,
    },
    ExclusionCategory.REVIEW_WITHOUT_RESOLUTION: {
        LedgerReasonCode.REVIEW_RESOLUTION_ABSENT,
    },
    ExclusionCategory.CALIBRATION_OR_PROBABILITY_UNAVAILABLE: {
        LedgerReasonCode.PROBABILITY_UNAVAILABLE,
        LedgerReasonCode.CALIBRATION_UNAVAILABLE,
    },
    ExclusionCategory.OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE: {
        LedgerReasonCode.EXTERNAL_RETAILER_REFERENCE_UNAVAILABLE,
    },
    ExclusionCategory.METRIC_NOT_ASSESSABLE: {
        LedgerReasonCode.EMPTY_DENOMINATOR,
        LedgerReasonCode.MANDATORY_EVIDENCE_UNAVAILABLE,
    },
    ExclusionCategory.CONFIGURATION_OR_FREEZE_FAILURE: {
        LedgerReasonCode.CONFIGURATION_INVALID,
        LedgerReasonCode.FREEZE_EVIDENCE_MISSING,
        LedgerReasonCode.PARTITION_CONTROL_FAILURE,
    },
}


@dataclass(frozen=True, slots=True)
class ExclusionLedgerEntry:
    """One typed, auditable offline reason without metric computation."""

    ledger_entry_id: str
    dataset_id: str
    dataset_tier: DatasetTier
    stage: LedgerStage
    category: ExclusionCategory
    reason_code: LedgerReasonCode
    reason_detail: str
    affected_metrics: tuple[str, ...]
    denominator_action: DenominatorAction
    audit_provenance: AuditProvenance
    partition_id: str | None = None
    cohort_id: str | None = None
    receipt_id: str | None = None
    item_row_id: str | None = None
    field_id: str | None = None
    run_id: str | None = None
    system_id: str | None = None
    configuration_id: str | None = None
    software_version: str | None = None
    schema_version: str = EXCLUSION_LEDGER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.ledger_entry_id, "ledger_entry_id")
        _require_identifier(self.dataset_id, "entry dataset_id")
        if not isinstance(self.dataset_tier, DatasetTier):
            raise TypeError("dataset_tier must be a DatasetTier.")
        if not isinstance(self.stage, LedgerStage):
            raise TypeError("stage must be a LedgerStage.")
        if not isinstance(self.category, ExclusionCategory):
            raise TypeError("category must be an ExclusionCategory.")
        if not isinstance(self.reason_code, LedgerReasonCode):
            raise TypeError("reason_code must be a LedgerReasonCode.")
        if not isinstance(self.denominator_action, DenominatorAction):
            raise TypeError("denominator_action must be a DenominatorAction.")
        _require_text(self.reason_detail, "reason_detail")
        if not isinstance(self.affected_metrics, tuple):
            raise TypeError("affected_metrics must be a tuple.")
        if not self.affected_metrics:
            raise ValueError("affected_metrics cannot be empty.")
        for metric in self.affected_metrics:
            _require_identifier(metric, "affected metric")
        if len(self.affected_metrics) != len(set(self.affected_metrics)):
            raise ValueError("affected_metrics must not contain duplicates.")
        if not isinstance(self.audit_provenance, AuditProvenance):
            raise TypeError("audit_provenance must be AuditProvenance.")
        for value, name in (
            (self.partition_id, "partition_id"),
            (self.cohort_id, "cohort_id"),
            (self.receipt_id, "receipt_id"),
            (self.item_row_id, "item_row_id"),
            (self.field_id, "field_id"),
            (self.run_id, "run_id"),
            (self.system_id, "system_id"),
            (self.configuration_id, "configuration_id"),
            (self.software_version, "software_version"),
        ):
            _require_optional_identifier(value, name)
        if self.item_row_id is not None and self.receipt_id is None:
            raise ValueError("item_row_id requires receipt_id.")
        if self.field_id is not None and self.receipt_id is None:
            raise ValueError("field_id requires receipt_id.")
        if (
            self.category is ExclusionCategory.DATASET_LEVEL_EXCLUSION
            and self.receipt_id is None
        ):
            raise ValueError("DATASET_LEVEL_EXCLUSION requires receipt_id.")
        if (
            self.category is not ExclusionCategory.DATASET_LEVEL_EXCLUSION
            and self.receipt_id is not None
        ):
            if self.partition_id is None or self.cohort_id is None:
                raise ValueError(
                    "Receipt-scoped ledger entries require partition and cohort IDs."
                )
        if self.stage is not _EXPECTED_STAGE[self.category]:
            raise ValueError("Ledger category is inconsistent with its stage.")
        if self.denominator_action is not _EXPECTED_ACTION[self.category]:
            raise ValueError(
                "Ledger category is inconsistent with its denominator action."
            )
        if self.reason_code not in _ALLOWED_REASONS[self.category]:
            raise ValueError("Ledger reason code is inconsistent with its category.")
        if self.category in {
            ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
            ExclusionCategory.SYSTEM_MISSING_PREDICTION,
        } and self.field_id is None:
            raise ValueError(f"{self.category.value} requires field_id.")
        if self.category in {
            ExclusionCategory.SYSTEM_MISSING_PREDICTION,
            ExclusionCategory.SYSTEM_FAILURE,
            ExclusionCategory.REVIEW_WITHOUT_RESOLUTION,
            ExclusionCategory.CALIBRATION_OR_PROBABILITY_UNAVAILABLE,
        } and (self.run_id is None or self.system_id is None):
            raise ValueError(
                f"{self.category.value} requires run_id and system_id."
            )
        if self.schema_version != EXCLUSION_LEDGER_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported exclusion-ledger schema version."
            )


@dataclass(frozen=True, slots=True)
class ExclusionLedger:
    """Versioned collection of typed offline reason entries."""

    ledger_id: str
    ledger_version: str
    manifest_id: str
    dataset_id: str
    dataset_tier: DatasetTier
    entries: tuple[ExclusionLedgerEntry, ...]
    provenance: AuditProvenance
    schema_version: str = EXCLUSION_LEDGER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.ledger_id, "ledger_id")
        _require_identifier(self.ledger_version, "ledger_version")
        _require_identifier(self.manifest_id, "manifest_id")
        _require_identifier(self.dataset_id, "ledger dataset_id")
        if not isinstance(self.dataset_tier, DatasetTier):
            raise TypeError("dataset_tier must be a DatasetTier.")
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple.")
        if any(not isinstance(item, ExclusionLedgerEntry) for item in self.entries):
            raise TypeError("entries contains an invalid ledger record.")
        if not isinstance(self.provenance, AuditProvenance):
            raise TypeError("provenance must be AuditProvenance.")
        entry_ids = tuple(item.ledger_entry_id for item in self.entries)
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("Duplicate exclusion-ledger entry IDs.")
        if self.schema_version != EXCLUSION_LEDGER_SCHEMA_VERSION:
            raise ValueError("Unsupported exclusion-ledger schema version.")


class ExclusionLedgerValidationError(ValueError):
    """Raised when ledger scope or independent-reference linkage is invalid."""


def _validation_fail(message: str) -> None:
    raise ExclusionLedgerValidationError(message)


def _reference_index(
    references: tuple[TierAReferenceReceipt, ...] | None,
) -> dict[str, TierAReferenceReceipt]:
    if references is None:
        return {}
    if not isinstance(references, tuple):
        raise TypeError("references must be a tuple.")
    result: dict[str, TierAReferenceReceipt] = {}
    for receipt in references:
        if not isinstance(receipt, TierAReferenceReceipt):
            raise TypeError("references contains an invalid reference receipt.")
        if receipt.receipt_id in result:
            _validation_fail(f"Duplicate reference receipt {receipt.receipt_id!r}.")
        result[receipt.receipt_id] = receipt
    return result


def _validate_reference_link(
    entry: ExclusionLedgerEntry,
    references: dict[str, TierAReferenceReceipt],
) -> None:
    truth_dependent = entry.category in {
        ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE,
        ExclusionCategory.SYSTEM_MISSING_PREDICTION,
    }
    if entry.receipt_id is None:
        if truth_dependent:
            _validation_fail(
                f"{entry.category.value} requires independent reference truth."
            )
        return
    if not references:
        if (
            truth_dependent
            or entry.item_row_id is not None
            or entry.field_id is not None
        ):
            _validation_fail(
                "Receipt/row/field ledger links require Task 2.5A references."
            )
        return

    receipt = references.get(entry.receipt_id)
    if receipt is None:
        if (
            entry.category is ExclusionCategory.DATASET_LEVEL_EXCLUSION
            and entry.item_row_id is None
            and entry.field_id is None
        ):
            return
        _validation_fail(
            f"Ledger entry {entry.ledger_entry_id!r} references an unknown receipt."
        )
    assert receipt is not None
    rows = {row.row_id: row for row in receipt.items}
    fields = {field.field_id: field for field in receipt.all_fields}
    if entry.item_row_id is not None and entry.item_row_id not in rows:
        _validation_fail(
            f"Ledger entry {entry.ledger_entry_id!r} references an unknown item row."
        )
    field = None
    if entry.field_id is not None:
        field = fields.get(entry.field_id)
        if field is None:
            _validation_fail(
                f"Ledger entry {entry.ledger_entry_id!r} references an unknown field."
            )
        assert field is not None
        if field.item_row_id != entry.item_row_id:
            _validation_fail(
                f"Ledger entry {entry.ledger_entry_id!r} has inconsistent field/row links."
            )

    if truth_dependent:
        assert field is not None
        adjudication_ids = {
            event.event_id for event in receipt.provenance.adjudication_events
        }
        if (
            field.adjudication_event_id is None
            or field.adjudication_event_id not in adjudication_ids
        ):
            _validation_fail(
                f"{entry.category.value} requires field-level adjudication evidence."
            )

    if entry.category is ExclusionCategory.REFERENCE_LABEL_UNAVAILABLE:
        assert field is not None
        if field.availability is not ReferenceAvailability.UNAVAILABLE:
            _validation_fail(
                "REFERENCE_LABEL_UNAVAILABLE contradicts reference-available truth."
            )
        if (
            entry.reason_code
            is LedgerReasonCode.UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE
            and field.field_name is not ReceiptFieldName.UNIT_PRICE
        ):
            _validation_fail(
                "UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE requires a unit-price field."
            )
    elif entry.category is ExclusionCategory.SYSTEM_MISSING_PREDICTION:
        assert field is not None
        if field.availability is not ReferenceAvailability.AVAILABLE:
            _validation_fail(
                "SYSTEM_MISSING_PREDICTION requires reference-available truth."
            )
    elif entry.category is ExclusionCategory.ADJUDICATION_PENDING:
        if receipt.status is ReferenceRecordStatus.FINALIZED:
            _validation_fail(
                "ADJUDICATION_PENDING contradicts a finalized reference receipt."
            )
        if field is not None and field.adjudication_event_id is not None:
            _validation_fail(
                "ADJUDICATION_PENDING field already has adjudication provenance."
            )
        if field is None and all(
            candidate.adjudication_event_id is not None
            for candidate in receipt.all_fields
        ):
            _validation_fail(
                "ADJUDICATION_PENDING receipt has no unresolved field provenance."
            )


def _validate_manifest_envelope(
    ledger: ExclusionLedger,
    manifest: EvaluationManifest,
) -> None:
    if ledger.manifest_id != manifest.manifest_id:
        _validation_fail("Ledger refers to another manifest.")
    if ledger.dataset_id != manifest.dataset_id:
        _validation_fail("Ledger refers to another dataset.")
    if ledger.dataset_tier is not manifest.dataset_tier:
        _validation_fail("Ledger and manifest dataset tiers conflict.")


def _validate_manifest_link(
    entry: ExclusionLedgerEntry,
    manifest: EvaluationManifest,
) -> None:
    partition_ids = {item.partition_id for item in manifest.partitions}
    cohorts = {item.cohort_id: set(item.receipt_ids) for item in manifest.cohorts}
    membership = {item.receipt_id: item.partition_id for item in manifest.receipts}
    if entry.partition_id is not None and entry.partition_id not in partition_ids:
        _validation_fail("Ledger entry references an unknown partition.")
    if entry.cohort_id is not None and entry.cohort_id not in cohorts:
        _validation_fail("Ledger entry references an unknown cohort.")
    if entry.receipt_id is None:
        return
    assigned_partition = membership.get(entry.receipt_id)
    if assigned_partition is None:
        if entry.category is ExclusionCategory.DATASET_LEVEL_EXCLUSION:
            if entry.partition_id is not None or entry.cohort_id is not None:
                _validation_fail(
                    "A prospectively excluded receipt cannot claim manifest membership."
                )
            return
        _validation_fail("Non-dataset ledger entry references a non-member receipt.")
    if entry.category is ExclusionCategory.DATASET_LEVEL_EXCLUSION:
        _validation_fail(
            "DATASET_LEVEL_EXCLUSION contradicts eligible manifest membership."
        )
    if entry.partition_id != assigned_partition:
        _validation_fail("Ledger receipt and partition assignments conflict.")
    if entry.cohort_id is not None and entry.receipt_id not in cohorts[entry.cohort_id]:
        _validation_fail("Ledger receipt is not a member of the stated cohort.")


def validate_exclusion_ledger(
    ledger: ExclusionLedger,
    *,
    manifest: EvaluationManifest | None = None,
    references: tuple[TierAReferenceReceipt, ...] | None = None,
) -> None:
    """Validate ledger scope and truth links without scoring any prediction."""

    if not isinstance(ledger, ExclusionLedger):
        raise TypeError("ledger must be an ExclusionLedger.")
    if manifest is not None:
        if not isinstance(manifest, EvaluationManifest):
            raise TypeError("manifest must be an EvaluationManifest.")
        _validate_manifest_envelope(ledger, manifest)
    reference_by_id = _reference_index(references)
    for entry in ledger.entries:
        if entry.dataset_id != ledger.dataset_id:
            _validation_fail(
                f"Ledger entry {entry.ledger_entry_id!r} belongs to another dataset."
            )
        if entry.dataset_tier is not ledger.dataset_tier:
            _validation_fail(
                f"Ledger entry {entry.ledger_entry_id!r} has another dataset tier."
            )
        if manifest is not None:
            _validate_manifest_link(entry, manifest)
        _validate_reference_link(entry, reference_by_id)


def serialize_exclusion_ledger(
    ledger: ExclusionLedger,
    *,
    manifest: EvaluationManifest | None = None,
    references: tuple[TierAReferenceReceipt, ...] | None = None,
) -> str:
    """Validate and serialize ledger entries in canonical identifier order."""

    validate_exclusion_ledger(
        ledger,
        manifest=manifest,
        references=references,
    )
    payload = to_json_compatible(ledger)
    payload["entries"] = sorted(
        payload["entries"], key=lambda item: item["ledger_entry_id"]
    )
    for entry in payload["entries"]:
        entry["affected_metrics"] = sorted(entry["affected_metrics"])
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = (
    "EXCLUSION_LEDGER_SCHEMA_VERSION",
    "DenominatorAction",
    "ExclusionCategory",
    "ExclusionLedger",
    "ExclusionLedgerEntry",
    "ExclusionLedgerValidationError",
    "LedgerReasonCode",
    "LedgerStage",
    "serialize_exclusion_ledger",
    "validate_exclusion_ledger",
)
