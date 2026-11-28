"""Trusted local composition inputs for the existing seven-field receipt method."""

from dataclasses import dataclass
from math import isfinite
import re

from evaluation.research_policy_v0 import (
    FitConfiguration, FrozenCalibration, FrozenScorer, VerificationPolicy,
)
from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.contracts import FEATURE_SLOT_ORDER
from pipeline.proposed.receipt_correction_v1 import ReceiptMethodConfig
from pipeline.proposed.receipt_research_v1 import FieldVerificationSettings, ReceiptVerification
from pipeline.proposed.receipt_resources_v1 import ReceiptResources


METHOD_ID = "PROPOSED_RECEIPT_V1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True, repr=False)
class OperationalReceiptMethodV1:
    configuration_sha256: str
    resources: ReceiptResources
    region: str | None
    correction_config: ReceiptMethodConfig
    verification: ReceiptVerification | None

    def __post_init__(self) -> None:
        if not _digest(self.configuration_sha256) or (
            self.region is not None and (type(self.region) is not str or not self.region.strip())
        ):
            raise ValueError("Receipt method configuration identity or region refused.")


def _digest(value):
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _members(value, names):
    if type(value) is not dict or value.keys() != set(names.split()):
        raise ValueError("Frozen verification artifact fields refused.")
    return value


def _finite(value):
    return type(value) in (int, float) and isfinite(value)


def decode_frozen_receipt_verification(value) -> ReceiptVerification:
    """Bind reviewed JSON records to the existing scorer, calibrator and field settings."""
    packet = _members(value, "scorer scorer_sha256 calibration calibration_sha256 field_settings")
    scorer_raw = _members(packet["scorer"], "membership_sha256 training_examples_sha256 configuration weights")
    weights = scorer_raw["weights"]
    if (type(weights) is not list or len(weights) != 1 + 2 * len(FEATURE_SLOT_ORDER)
            or not all(_finite(weight) for weight in weights)
            or not all(_digest(scorer_raw[name]) for name in ("membership_sha256", "training_examples_sha256"))):
        raise ValueError("Frozen scorer records refused.")
    scorer = FrozenScorer(**{
        **scorer_raw, "configuration": FitConfiguration(**scorer_raw["configuration"]), "weights": tuple(weights),
    })
    calibration_raw = _members(
        packet["calibration"], "scorer_sha256 validation_predictions_sha256 configuration center scale intercept slope",
    )
    if (not _digest(calibration_raw["validation_predictions_sha256"])
            or not all(_finite(calibration_raw[name]) for name in ("center", "scale", "intercept", "slope"))
            or calibration_raw["scale"] <= 0 or calibration_raw["slope"] <= 0):
        raise ValueError("Frozen calibration records refused.")
    calibration = FrozenCalibration(**{
        **calibration_raw, "configuration": FitConfiguration(**calibration_raw["configuration"]),
    })
    if packet["scorer_sha256"] != scorer.sha256 or packet["calibration_sha256"] != calibration.sha256:
        raise ValueError("Frozen scorer or calibration identity refused.")

    roles = _members(packet["field_settings"], " ".join(role.value for role in ReceiptFieldName))
    settings = {}
    for role, raw in roles.items():
        row = _members(raw, "pantry_relevant policy replacement_margin unresolved_conflict")
        margin = row["replacement_margin"]
        if (not _finite(margin) or not 0 <= margin <= 1
                or any(type(row[name]) is not bool for name in ("pantry_relevant", "unresolved_conflict"))):
            raise ValueError("Frozen field verification settings refused.")
        settings[ReceiptFieldName(role)] = FieldVerificationSettings(
            **{**row, "policy": VerificationPolicy(**row["policy"])},
        )

    return ReceiptVerification(scorer, calibration, lambda field: settings[field.original.field_name])
