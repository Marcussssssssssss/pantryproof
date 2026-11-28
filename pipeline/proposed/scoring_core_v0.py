"""Standalone E01 M1-M3 numerical scoring for synthetic purchase dates.

The artifact is verified by content. The result makes no parent Theta_A
binding, operational admission, trusted scorer or probability claim.
"""

from dataclasses import dataclass
from decimal import (
    Clamped,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)
from hashlib import sha256
import json
from typing import Any

from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.feature_construction import (
    CandidateFeatureVectorV0,
    FeatureSlotValueV0,
    FeatureValueAvailabilityV0,
)


SYNTHETIC_SCORING_ARTIFACT_V0 = (
    b'{"center":"0.5","coefficient_digits_max":64,"encoded_precision":7,'
    b'"encoded_scale":6,"exponent_min":-400,"intercept":"0",'
    b'"method":"purchase-date-centered-affine-margin-v0","rounding":"ROUND_HALF_EVEN",'
    b'"scope":"synthetic_only","slot_order":["q_o","q_e","a_l","a_y","s_r","s_a","s_p"],'
    b'"theta_a_artifact":"pantryproof.theta-a.e01.purchase-date.synthetic",'
    b'"version":"0.1.0","weights":["1",null,"2",null,null,null,null],"working_precision":420}'
)
SYNTHETIC_SCORING_ARTIFACT_SHA256 = (
    "9ebc6fbf9c1bea13215dc2cf455eb1bc4193c98ba134ea3e0ba52186da486ce1"
)


class SyntheticScoringError(ValueError):
    """An invalid synthetic score input or unrepresentable result."""


@dataclass(frozen=True, slots=True)
class SyntheticRawScoreV0:
    """A local raw margin retaining the exact FC01 vector and artifact identity."""

    feature_vector: CandidateFeatureVectorV0
    raw_score: Decimal
    artifact_id: str
    artifact_version: str
    artifact_sha256: str


def _active_value(slot: FeatureSlotValueV0, parameters: dict[str, Any]) -> Decimal | None:
    if slot.availability is FeatureValueAvailabilityV0.MISSING:
        return None
    if slot.availability is not FeatureValueAvailabilityV0.AVAILABLE:
        raise SyntheticScoringError(f"{slot.slot.value} cannot be NOT_APPLICABLE.")
    value = slot.value
    if type(value) is not Decimal or not value.is_finite() or not 0 <= value <= 1:
        raise SyntheticScoringError(f"{slot.slot.value} must be a finite Decimal in [0, 1].")
    representation = value.as_tuple()
    if (
        len(representation.digits) > parameters["coefficient_digits_max"]
        or not parameters["exponent_min"] <= representation.exponent <= 0
    ):
        raise SyntheticScoringError(f"{slot.slot.value} exceeds the approved Decimal bounds.")
    return value


def _score_slots(
    slots: tuple[FeatureSlotValueV0, ...], parameters: dict[str, Any]
) -> Decimal:
    if tuple(slot.slot.value for slot in slots) != tuple(parameters["slot_order"]):
        raise SyntheticScoringError("FC01 slot order differs from the synthetic scoring artifact.")
    context = Context(
        prec=parameters["working_precision"],
        Emin=-999,
        Emax=999,
        clamp=0,
        rounding=parameters["rounding"],
        traps=[
            Clamped, DivisionByZero, FloatOperation, Inexact, InvalidOperation,
            Overflow, Rounded, Subnormal, Underflow,
        ],
    )
    center = Decimal(parameters["center"])
    quantum = Decimal((0, (1,), -parameters["encoded_scale"]))
    try:
        with localcontext(context) as working:
            margin = Decimal(parameters["intercept"])
            usable = False
            for slot, weight in zip(slots, parameters["weights"], strict=True):
                if weight is None:
                    continue
                value = _active_value(slot, parameters)
                if value is None:
                    continue
                margin += Decimal(weight) * (value - center)
                usable = True
            if not usable:
                raise SyntheticScoringError("No usable active feature for synthetic scoring.")
            working.traps[Inexact] = False
            working.traps[Rounded] = False
            score = margin.quantize(quantum)
    except DecimalException as exc:
        raise SyntheticScoringError("Synthetic scoring failed Decimal arithmetic.") from exc

    if len(score.as_tuple().digits) > parameters["encoded_precision"]:
        raise SyntheticScoringError("Synthetic score exceeds the approved output precision.")
    return score.copy_abs() if score.is_zero() else score


def score_synthetic_purchase_date_v0(
    *,
    feature_vector: CandidateFeatureVectorV0,
    artifact_bytes: bytes = SYNTHETIC_SCORING_ARTIFACT_V0,
) -> SyntheticRawScoreV0:
    """Score one eligible FC01 vector using the exact standalone E01 artifact."""

    if (
        type(artifact_bytes) is not bytes
        or len(artifact_bytes) != 438
        or sha256(artifact_bytes).hexdigest() != SYNTHETIC_SCORING_ARTIFACT_SHA256
    ):
        raise SyntheticScoringError("Synthetic scoring artifact identity mismatch.")
    parameters = json.loads(artifact_bytes)
    if type(feature_vector) is not CandidateFeatureVectorV0:
        raise SyntheticScoringError("Expected one source-bound FC01 candidate feature vector.")
    try:
        field_name = feature_vector.candidate_audit.target_field.field_name
        if field_name is ReceiptFieldName.PURCHASE_DATE:
            feature_vector.__post_init__()
    except (AttributeError, TypeError, ValueError, DecimalException) as exc:
        raise SyntheticScoringError("FC01 feature vector failed source revalidation.") from exc
    if field_name is not ReceiptFieldName.PURCHASE_DATE:
        raise SyntheticScoringError("Synthetic scoring is defined only for purchase dates.")

    return SyntheticRawScoreV0(
        feature_vector=feature_vector,
        raw_score=_score_slots(feature_vector.slot_values, parameters),
        artifact_id=parameters["theta_a_artifact"],
        artifact_version=parameters["version"],
        artifact_sha256=SYNTHETIC_SCORING_ARTIFACT_SHA256,
    )
