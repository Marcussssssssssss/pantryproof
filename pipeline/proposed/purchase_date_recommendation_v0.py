"""Opt-in purchase-date recommendations over retained candidates and OCR anchors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pipeline.baseline_b3 import B3ParseState
from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.candidate_deduplication import normalize_candidate_value
from pipeline.proposed.contracts import CandidateRecordV1, CandidateSourceKind
from pipeline.proposed.feature_construction import FeatureConstructionResultV0
from pipeline.proposed.purchase_date_source_contracts_v1 import (
    DateDiscoveryMethodProfileV1,
    DateObservationKindV1,
    DateSourceObservationV1,
)
from pipeline.proposed.purchase_date_source_discovery_v1 import discover_purchase_date_sources_v1
from pipeline.proposed.scoring_input_preparation import prepare_scoring_source_snapshot_v2


class PurchaseDateRecommendationStatusV0(str, Enum):
    PREFER_ALTERNATIVE = "PREFER_ALTERNATIVE"
    KEEP_ORIGINAL = "KEEP_ORIGINAL"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class PurchaseDateRecommendationReasonV0(str, Enum):
    ANCHOR_SUPPORTS_ALTERNATIVE = "ANCHOR_SUPPORTS_ALTERNATIVE"
    ANCHOR_CONFIRMS_ORIGINAL = "ANCHOR_CONFIRMS_ORIGINAL"
    ORIGINAL_NOT_ELIGIBLE = "ORIGINAL_NOT_ELIGIBLE"
    NO_DATE_ANCHOR = "NO_DATE_ANCHOR"
    AMBIGUOUS_DATE_ANCHORS = "AMBIGUOUS_DATE_ANCHORS"
    NO_UNIQUE_ELIGIBLE_MATCH = "NO_UNIQUE_ELIGIBLE_MATCH"
    ALTERNATIVE_LACKS_ANCHOR_PROVENANCE = "ALTERNATIVE_LACKS_ANCHOR_PROVENANCE"


@dataclass(frozen=True, slots=True, repr=False)
class PurchaseDateRecommendationV0:
    status: PurchaseDateRecommendationStatusV0
    reason: PurchaseDateRecommendationReasonV0
    original: CandidateRecordV1
    preferred: CandidateRecordV1 | None
    source_snapshot_id: str
    anchors: tuple[DateSourceObservationV1, ...]


def recommend_purchase_date_v0(
    *,
    features: FeatureConstructionResultV0,
    discovery_profile: DateDiscoveryMethodProfileV1,
) -> PurchaseDateRecommendationV0:
    """Compare retained eligible candidates against agreeing explicit date anchors.

    D1 observes the exact retained B2 image and OCR records. D3 and FC01
    determine eligibility. An altered match must also cite a body span that
    supports its value. The comparison uses the existing candidate limit and
    D1 discovery bounds. This local recommendation leaves the original and
    downstream state intact. Upstream validation errors propagate.
    """
    snapshot = prepare_scoring_source_snapshot_v2(feature_construction_result=features)
    original = snapshot.c0_candidate
    eligible = snapshot.candidate_features
    anchors: tuple[DateSourceObservationV1, ...] = ()

    def review(reason: PurchaseDateRecommendationReasonV0) -> PurchaseDateRecommendationV0:
        return PurchaseDateRecommendationV0(
            PurchaseDateRecommendationStatusV0.MANUAL_REVIEW, reason,
            original, None, snapshot.source_snapshot_id, anchors,
        )

    if not any(vector.candidate is original for vector in eligible):
        return review(PurchaseDateRecommendationReasonV0.ORIGINAL_NOT_ELIGIBLE)

    context = features.operand_audit.hard_constraint_input
    discovery = discover_purchase_date_sources_v1(
        source_evidence=context.receipt_output.source_evidence,
        b2_result=context.adapter_result.original_b2_result,
        theta_a_reference=snapshot.theta_a_reference,
        method_profile=discovery_profile,
        existing_c0=original,
    )
    anchors = tuple(
        observation for observation in discovery.observations
        if observation.observation_kind is not DateObservationKindV1.WHOLE_TOKEN
    )
    if not anchors:
        return review(PurchaseDateRecommendationReasonV0.NO_DATE_ANCHOR)

    derivations = {item.observation_id: item for item in discovery.derivations}
    readings: set[str] = set()
    for anchor in anchors:
        interpretation = derivations.get(anchor.observation_id)
        if (
            interpretation is None
            or interpretation.parse_state is not B3ParseState.VALID
            or interpretation.normalized_value is None
        ):
            return review(PurchaseDateRecommendationReasonV0.AMBIGUOUS_DATE_ANCHORS)
        readings.add(interpretation.normalized_value)
    if len(readings) != 1:
        return review(PurchaseDateRecommendationReasonV0.AMBIGUOUS_DATE_ANCHORS)

    key = normalize_candidate_value(
        field_name=ReceiptFieldName.PURCHASE_DATE, exact_value=next(iter(readings)),
    ).normalized_key
    matches = tuple(
        vector.candidate for vector in eligible if vector.candidate.normalized_dedup_key == key
    )
    if len(matches) != 1:
        return review(PurchaseDateRecommendationReasonV0.NO_UNIQUE_ELIGIBLE_MATCH)
    (preferred,) = matches
    if preferred is original:
        return PurchaseDateRecommendationV0(
            PurchaseDateRecommendationStatusV0.KEEP_ORIGINAL,
            PurchaseDateRecommendationReasonV0.ANCHOR_CONFIRMS_ORIGINAL,
            original, original, snapshot.source_snapshot_id, anchors,
        )

    anchor_bodies = {
        anchor.source_token.token_id: anchor.body_span
        for anchor in anchors if anchor.body_span is not None
    }
    for provenance in preferred.provenance:
        if provenance.source_kind is not CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR:
            continue
        for span in provenance.source_spans:
            body = anchor_bodies.get(span.token_id)
            if body is not None and span.start <= body.start < body.end <= span.end:
                return PurchaseDateRecommendationV0(
                    PurchaseDateRecommendationStatusV0.PREFER_ALTERNATIVE,
                    PurchaseDateRecommendationReasonV0.ANCHOR_SUPPORTS_ALTERNATIVE,
                    original, preferred, snapshot.source_snapshot_id, anchors,
                )
    return review(PurchaseDateRecommendationReasonV0.ALTERNATIVE_LACKS_ANCHOR_PROVENANCE)
