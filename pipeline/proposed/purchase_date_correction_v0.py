"""Development-only correction of an extracted B2 purchase date."""

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json

from pipeline.baseline_b3 import B3ParseState, parse_generic_date
from pipeline.contracts import FieldStatus, ReceiptOutput
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed.adapter import adapt_b2_to_proposed
from pipeline.proposed.backend_observational_path import execute_purchase_date_discovery_graph_v0
from pipeline.proposed.candidate_limiting import CandidateLimitingConfigurationV0
from pipeline.proposed.candidate_ranking import CandidateRankingConfigurationV0
from pipeline.proposed.contracts import (
    CandidateSourceKind, ConfigurationKind, ConfigurationRefV1, ConfigurationState,
    MethodReadyFieldV1,
)
from pipeline.proposed.feature_construction import (
    FeatureConstructionResultV0, construct_purchase_date_features_v0,
)
from pipeline.proposed.hard_constraint_contracts_v2 import (
    HardConstraintProfileRefV2, HardConstraintRuleSpecV2, RuleRequirementV2,
)
from pipeline.proposed.purchase_date_calendar_validity import (
    PURCHASE_DATE_APPLICABILITY_REFERENCE, PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION, PURCHASE_DATE_GRAMMAR_REFERENCE,
    PURCHASE_DATE_PROFILE_ID, PURCHASE_DATE_PROFILE_VERSION,
)
from pipeline.proposed.purchase_date_recommendation_v0 import (
    PurchaseDateRecommendationStatusV0, PurchaseDateRecommendationV0, recommend_purchase_date_v0,
)
from pipeline.proposed.purchase_date_source_contracts_v1 import (
    DateDiscoveryError, DateDiscoveryResultV1, DateObservationKindV1,
    make_purchase_date_discovery_profile_v1,
)
from pipeline.proposed.purchase_date_source_discovery_v1 import discover_purchase_date_sources_v1
from pipeline.proposed.scoring_core_v0 import (
    SYNTHETIC_SCORING_ARTIFACT_SHA256, SyntheticRawScoreV0, SyntheticScoringError,
    score_synthetic_purchase_date_v0,
)
from pipeline.proposed.suspicion import (
    ConfidenceAggregationV0, ConfidenceRuleV0, SuspicionConfigurationV0, SuspicionContextV0,
    SuspicionResultV0, UpstreamObservationStateV0, UpstreamObservationV0, UpstreamSignalV0,
    detect_suspicion,
)


PRODUCER_ID = "B2_PURCHASE_DATE_CORRECTION"
PRODUCER_VERSION = "purchase-date-correction-development-v0"
_OCR_CONFIDENCE_FLOOR = Decimal("0.50")
_CANDIDATE_LIMIT = 4  # Includes c0.
_MAX_ANCHORED_OBSERVATIONS = 8
_CONFIGURATION = {
    "candidate_limit": _CANDIDATE_LIMIT,
    "max_anchored_observations": _MAX_ANCHORED_OBSERVATIONS,
    "raw_confidence_floor": str(_OCR_CONFIDENCE_FLOOR),
    "selection": "unanimous-valid-anchored-body-v0",
    "diagnostic_score_sha256": SYNTHETIC_SCORING_ARTIFACT_SHA256,
}
_THETA = ConfigurationRefV1(
    kind=ConfigurationKind.THETA_A,
    configuration_id="purchase-date-correction-development",
    configuration_version=PRODUCER_VERSION,
    state=ConfigurationState.READY,
    content_hash="sha256:" + sha256(json.dumps(_CONFIGURATION, sort_keys=True).encode()).hexdigest(),
)
_CALENDAR = HardConstraintProfileRefV2(
    profile_id=PURCHASE_DATE_PROFILE_ID,
    profile_version=PURCHASE_DATE_PROFILE_VERSION,
    theta_a_reference=_THETA,
    ordered_rule_specs=(HardConstraintRuleSpecV2(
        rule_id=PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID,
        rule_version=PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION,
        position=0,
        requirement=RuleRequirementV2.MANDATORY,
        applicability_reference=PURCHASE_DATE_APPLICABILITY_REFERENCE,
    ),),
)


class PurchaseDateCorrectionOutcomeV0(str, Enum):
    CORRECT = "CORRECT"
    PRESERVE = "PRESERVE"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True, slots=True, repr=False)
class PurchaseDateCorrectionResultV0:
    """Request-scoped evidence. The B2 result, OCR tokens, and c0 stay intact."""

    baseline: B2ExtractionResult
    final_output: ReceiptOutput | None
    outcome: PurchaseDateCorrectionOutcomeV0
    reason: str
    discovery: DateDiscoveryResultV1 | None = None
    suspicion: SuspicionResultV0 | None = None
    features: FeatureConstructionResultV0 | None = None
    scores: tuple[SyntheticRawScoreV0, ...] = ()
    recommendation: PurchaseDateRecommendationV0 | None = None


def _suspicion(method: MethodReadyFieldV1, discovery: DateDiscoveryResultV1) -> SuspicionResultV0:
    parsed = parse_generic_date(method.c0_value)
    state = UpstreamObservationStateV0
    signal = UpstreamSignalV0
    source = method.original_b2_field.field_id

    def observation(kind, status, evidence_ids=(), reason=None):
        return UpstreamObservationV0(
            f"{source}:{kind.value}:correction-v0", method.receipt_id, source, kind,
            status, PRODUCER_ID, PRODUCER_VERSION, evidence_ids, reason,
        )

    anchors = tuple(item for item in discovery.observations
                    if item.observation_kind is not DateObservationKindV1.WHOLE_TOKEN)
    readings = {item.observation_id: item.normalized_value for item in discovery.derivations}
    if not anchors:
        association = observation(signal.LINE_ASSOCIATION, state.UNAVAILABLE,
                                  reason="No explicit date label was observed.")
    else:
        evidence_ids = tuple(item.observation_id for item in anchors)
        if parsed.normalized_value is not None and all(
            readings.get(item.observation_id) == parsed.normalized_value for item in anchors
        ):
            association = observation(signal.LINE_ASSOCIATION, state.PASS, evidence_ids)
        else:
            association = observation(
                signal.LINE_ASSOCIATION, state.FAIL, evidence_ids,
                "Explicit date evidence disagrees with the B2 reading or is unclear.",
            )
    parse_check = (
        observation(signal.PARSE_TYPE, state.PASS, (source,))
        if parsed.state is B3ParseState.VALID
        else observation(signal.PARSE_TYPE, state.FAIL, (source,), "B2 date has no unique valid parse.")
    )
    context = SuspicionContextV0(
        context_id=f"{method.method_field_id}:correction-v0",
        receipt_id=method.receipt_id, method_field_id=method.method_field_id, field_id=source,
        gate_result_id=method.stored_gate_result.gate_result_id,
        source_image_id=method.source_image_id, source_token_ids=method.source_token_ids,
        ocr_confidence_source="OCR_NATIVE", context_builder_id=PRODUCER_ID,
        context_builder_version=PRODUCER_VERSION,
        required_content=observation(signal.REQUIRED_CONTENT, state.PASS, (source,)),
        parse_type=parse_check, line_association=association,
        arithmetic=observation(signal.ARITHMETIC, state.NOT_APPLICABLE,
                               reason="No arithmetic condition applies to the purchase date."),
    )
    config = SuspicionConfigurationV0(
        theta_a_ref=_THETA,
        ocr_confidence_rule=ConfidenceRuleV0(
            "purchase-date-ocr-confidence", context.ocr_confidence_source,
            ConfidenceAggregationV0.MIN_ALL_REFERENCED, _OCR_CONFIDENCE_FLOOR,
            Decimal("0"), Decimal("1"),
        ),
        extractor_confidence_rule=ConfidenceRuleV0(
            "purchase-date-extractor-confidence", method.b2_extractor_version,
            ConfidenceAggregationV0.DIRECT, _OCR_CONFIDENCE_FLOOR, Decimal("0"), Decimal("1"),
        ),
        context_builder_id=PRODUCER_ID, context_builder_version=PRODUCER_VERSION,
    )
    return detect_suspicion(method, context, config)


def correct_purchase_date_v0(
    baseline: B2ExtractionResult, *, include_diagnostic_scores: bool = True,
) -> PurchaseDateCorrectionResultV0:
    """Choose one anchored, eligible alternative or retain the exact baseline.

    Existing raw margins are development evidence. Explicit source agreement
    decides replacement because the raw margin rewards similarity to c0.
    """
    output = baseline.receipt_output
    decision = PurchaseDateCorrectionOutcomeV0
    result = PurchaseDateCorrectionResultV0(
        baseline, output, decision.ABSTAIN, "NO_STRUCTURED_BASELINE",
    )
    if output is None:
        return result
    if output.purchase_date.status is not FieldStatus.EXTRACTED:
        return replace(result, reason="DATE_NOT_EXTRACTED")

    try:
        profile = make_purchase_date_discovery_profile_v1(_THETA)
        discovery = discover_purchase_date_sources_v1(
            source_evidence=output.source_evidence, b2_result=baseline,
            theta_a_reference=_THETA, method_profile=profile,
        )
    except DateDiscoveryError as error:
        return replace(result, reason=f"DATE_DISCOVERY_{error.code.value}")

    adapter = adapt_b2_to_proposed(baseline)
    method = next(field for field in adapter.method_ready_fields
                  if field.original_b2_field is output.purchase_date)
    suspicion = _suspicion(method, discovery)
    result = replace(result, discovery=discovery, suspicion=suspicion)
    if sum(item.observation_kind is not DateObservationKindV1.WHOLE_TOKEN
           for item in discovery.observations) > _MAX_ANCHORED_OBSERVATIONS:
        return replace(result, reason="DATE_ANCHOR_LIMIT_EXCEEDED")

    audit, constraints = execute_purchase_date_discovery_graph_v0(
        adapter_result=adapter, suspicion_result=suspicion, date_discovery=discovery,
        ranking_configuration=CandidateRankingConfigurationV0(theta_a_ref=_THETA),
        limiting_configuration=CandidateLimitingConfigurationV0(
            theta_a_ref=_THETA, candidate_limit=_CANDIDATE_LIMIT, fixture_reference=PRODUCER_VERSION,
        ),
        rule_profile_reference=_CALENDAR, grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
    )
    features = construct_purchase_date_features_v0(operand_audit=audit, constraint_results=constraints)
    result = replace(result, features=features)
    scores = ()
    if include_diagnostic_scores:
        try:
            scores = tuple(score_synthetic_purchase_date_v0(feature_vector=vector)
                           for vector in features.candidate_features)
        except SyntheticScoringError:
            return replace(result, reason="DEVELOPMENT_SCORING_REFUSED")
    recommendation = recommend_purchase_date_v0(features=features, discovery_profile=profile)
    result = replace(result, scores=scores, recommendation=recommendation,
                     reason=recommendation.reason.value)
    if recommendation.status is PurchaseDateRecommendationStatusV0.KEEP_ORIGINAL:
        return replace(result, outcome=decision.PRESERVE)
    if recommendation.status is not PurchaseDateRecommendationStatusV0.PREFER_ALTERNATIVE:
        return result

    preferred = recommendation.preferred
    if preferred is None or not suspicion.is_suspicious:
        return replace(result, reason="NO_SUSPICIOUS_ANCHORED_ALTERNATIVE")
    source_ids = tuple(dict.fromkeys(
        span.token_id
        for provenance in preferred.provenance
        if provenance.source_kind is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR
        for span in provenance.source_spans
    ))
    corrected = replace(
        output,
        purchase_date=replace(output.purchase_date, value=preferred.value,
                              source_token_ids=source_ids, confidence=None),
        extractor_version=PRODUCER_VERSION,
    )
    return replace(result, final_output=corrected, outcome=decision.CORRECT)
