"""Deterministic upstream suspicion detection for proposed-method fields.

This component consumes one already-valid ``MethodReadyFieldV1``.  It does not
generate candidates, score or calibrate them, route review, or create receipt
dispositions.  A result with no reasons only means that altered candidate
generation is not requested; permanent original candidate c0 remains intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from math import isfinite

from pipeline.contracts import FieldStatus, SourceEvidenceDecision
from pipeline.proposed.contracts import (
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    MethodReadyFieldV1,
)


SUSPICION_RECORD_VERSION = "0"
SUSPICION_DETECTOR_VERSION = "suspicion-v0"


class SuspicionIntegrityError(ValueError):
    """Stored component inputs cannot form a trustworthy suspicion result."""


class SuspicionReasonCode(str, Enum):
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    LOW_EXTRACTOR_CONFIDENCE = "LOW_EXTRACTOR_CONFIDENCE"
    MISSING_REQUIRED_CONTENT = "MISSING_REQUIRED_CONTENT"
    PARSE_TYPE_FAILURE = "PARSE_TYPE_FAILURE"
    LINE_ASSOCIATION_CONFLICT = "LINE_ASSOCIATION_CONFLICT"
    ARITHMETIC_CONTRADICTION = "ARITHMETIC_CONTRADICTION"


SUSPICION_REASON_ORDER = tuple(SuspicionReasonCode)


class ConfidenceAggregationV0(str, Enum):
    MIN_ALL_REFERENCED = "MIN_ALL_REFERENCED"
    DIRECT = "DIRECT"


class ConfidenceAvailabilityV0(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class UpstreamSignalV0(str, Enum):
    REQUIRED_CONTENT = "REQUIRED_CONTENT"
    PARSE_TYPE = "PARSE_TYPE"
    LINE_ASSOCIATION = "LINE_ASSOCIATION"
    ARITHMETIC = "ARITHMETIC"


class UpstreamObservationStateV0(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


_SIGNAL_REASON = {
    UpstreamSignalV0.REQUIRED_CONTENT: SuspicionReasonCode.MISSING_REQUIRED_CONTENT,
    UpstreamSignalV0.PARSE_TYPE: SuspicionReasonCode.PARSE_TYPE_FAILURE,
    UpstreamSignalV0.LINE_ASSOCIATION: (
        SuspicionReasonCode.LINE_ASSOCIATION_CONFLICT
    ),
    UpstreamSignalV0.ARITHMETIC: SuspicionReasonCode.ARITHMETIC_CONTRADICTION,
}


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty.")


def _require_unique(values: tuple[str, ...], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates.")


def _require_finite_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal.")


@dataclass(frozen=True, slots=True)
class ConfidenceRuleV0:
    """One explicit native-score rule owned by the referenced Theta_A."""

    rule_id: str
    score_source: str
    aggregation: ConfidenceAggregationV0
    threshold: Decimal
    domain_minimum: Decimal
    domain_maximum: Decimal
    record_version: str = SUSPICION_RECORD_VERSION

    def __post_init__(self) -> None:
        _require_text(self.rule_id, "rule_id")
        _require_text(self.score_source, "score_source")
        if not isinstance(self.aggregation, ConfidenceAggregationV0):
            raise ValueError("aggregation must be a ConfidenceAggregationV0 value.")
        _require_finite_decimal(self.threshold, "threshold")
        _require_finite_decimal(self.domain_minimum, "domain_minimum")
        _require_finite_decimal(self.domain_maximum, "domain_maximum")
        if self.domain_minimum > self.domain_maximum:
            raise ValueError("confidence domain minimum must not exceed maximum.")
        if not self.domain_minimum <= self.threshold <= self.domain_maximum:
            raise ValueError("confidence threshold must lie inside its declared domain.")
        if self.record_version != SUSPICION_RECORD_VERSION:
            raise ValueError("Unsupported suspicion record version.")


@dataclass(frozen=True, slots=True)
class ConfidenceEvidenceV0:
    """One source confidence value, or its explicit absence."""

    evidence_id: str
    value: Decimal | None
    record_version: str = SUSPICION_RECORD_VERSION

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence_id")
        if self.value is not None:
            _require_finite_decimal(self.value, "value")
        if self.record_version != SUSPICION_RECORD_VERSION:
            raise ValueError("Unsupported suspicion record version.")


@dataclass(frozen=True, slots=True)
class ConfidenceObservationV0:
    """Complete confidence vector, missingness and aggregate used by detection."""

    rule_id: str
    score_source: str
    aggregation: ConfidenceAggregationV0
    availability: ConfidenceAvailabilityV0
    evidence: tuple[ConfidenceEvidenceV0, ...]
    aggregate: Decimal | None
    missing_evidence_ids: tuple[str, ...]
    record_version: str = SUSPICION_RECORD_VERSION

    def __post_init__(self) -> None:
        _require_text(self.rule_id, "rule_id")
        _require_text(self.score_source, "score_source")
        if not isinstance(self.aggregation, ConfidenceAggregationV0):
            raise ValueError("aggregation must be a ConfidenceAggregationV0 value.")
        if not isinstance(self.availability, ConfidenceAvailabilityV0):
            raise ValueError("availability must be a ConfidenceAvailabilityV0 value.")
        if not self.evidence:
            raise ValueError("A confidence observation requires source evidence.")
        if any(not isinstance(item, ConfidenceEvidenceV0) for item in self.evidence):
            raise TypeError("evidence must contain ConfidenceEvidenceV0 records.")
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        _require_unique(evidence_ids, "confidence evidence IDs")
        _require_unique(self.missing_evidence_ids, "missing_evidence_ids")
        actual_missing = tuple(
            item.evidence_id for item in self.evidence if item.value is None
        )
        if self.missing_evidence_ids != actual_missing:
            raise ValueError(
                "missing_evidence_ids must exactly identify absent confidence values."
            )

        if self.availability is ConfidenceAvailabilityV0.AVAILABLE:
            if actual_missing or self.aggregate is None:
                raise ValueError("AVAILABLE confidence requires every value and aggregate.")
            _require_finite_decimal(self.aggregate, "aggregate")
            values = tuple(item.value for item in self.evidence)
            assert all(value is not None for value in values)
            available_values = tuple(value for value in values if value is not None)
            expected = (
                min(available_values)
                if self.aggregation is ConfidenceAggregationV0.MIN_ALL_REFERENCED
                else available_values[0]
            )
            if self.aggregation is ConfidenceAggregationV0.DIRECT and len(values) != 1:
                raise ValueError("DIRECT confidence requires exactly one evidence value.")
            if self.aggregate != expected:
                raise ValueError("confidence aggregate does not match its declared rule.")
        elif self.aggregate is not None or not actual_missing:
            raise ValueError(
                "UNAVAILABLE confidence requires a missing value and no aggregate."
            )
        if self.record_version != SUSPICION_RECORD_VERSION:
            raise ValueError("Unsupported suspicion record version.")


@dataclass(frozen=True, slots=True)
class UpstreamObservationV0:
    """One evidence-backed non-confidence check supplied by the orchestrator."""

    observation_id: str
    receipt_id: str
    field_id: str
    signal: UpstreamSignalV0
    state: UpstreamObservationStateV0
    provider_id: str
    provider_version: str
    evidence_ids: tuple[str, ...] = ()
    reason: str | None = None
    record_version: str = SUSPICION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.signal, UpstreamSignalV0):
            raise ValueError("signal must be an UpstreamSignalV0 value.")
        if not isinstance(self.state, UpstreamObservationStateV0):
            raise ValueError("state must be an UpstreamObservationStateV0 value.")
        for name in (
            "observation_id",
            "receipt_id",
            "field_id",
            "provider_id",
            "provider_version",
        ):
            _require_text(getattr(self, name), name)
        _require_unique(self.evidence_ids, "evidence_ids")
        if any(not isinstance(item, str) or not item.strip() for item in self.evidence_ids):
            raise ValueError("evidence_ids must contain non-empty strings.")

        if self.state is UpstreamObservationStateV0.PASS:
            if not self.evidence_ids or self.reason is not None:
                raise ValueError("PASS requires evidence IDs and no failure reason.")
        elif self.state is UpstreamObservationStateV0.FAIL:
            if not self.evidence_ids:
                raise ValueError("FAIL requires evidence IDs.")
            _require_text(self.reason or "", "reason")
        else:
            if self.evidence_ids:
                raise ValueError(
                    "UNAVAILABLE/NOT_APPLICABLE observations cannot claim evidence IDs."
                )
            _require_text(self.reason or "", "reason")
        if self.record_version != SUSPICION_RECORD_VERSION:
            raise ValueError("Unsupported suspicion record version.")


@dataclass(frozen=True, slots=True)
class SuspicionContextV0:
    """Identity-bound context for the four orchestrator-owned upstream checks."""

    context_id: str
    receipt_id: str
    method_field_id: str
    field_id: str
    gate_result_id: str
    source_image_id: str
    source_token_ids: tuple[str, ...]
    ocr_confidence_source: str
    context_builder_id: str
    context_builder_version: str
    required_content: UpstreamObservationV0
    parse_type: UpstreamObservationV0
    line_association: UpstreamObservationV0
    arithmetic: UpstreamObservationV0
    record_version: str = SUSPICION_RECORD_VERSION

    def __post_init__(self) -> None:
        for name in (
            "context_id",
            "receipt_id",
            "method_field_id",
            "field_id",
            "gate_result_id",
            "source_image_id",
            "ocr_confidence_source",
            "context_builder_id",
            "context_builder_version",
        ):
            _require_text(getattr(self, name), name)
        if not self.source_token_ids:
            raise ValueError("source_token_ids must not be empty.")
        _require_unique(self.source_token_ids, "source_token_ids")

        expected = (
            (self.required_content, UpstreamSignalV0.REQUIRED_CONTENT),
            (self.parse_type, UpstreamSignalV0.PARSE_TYPE),
            (self.line_association, UpstreamSignalV0.LINE_ASSOCIATION),
            (self.arithmetic, UpstreamSignalV0.ARITHMETIC),
        )
        for observation, signal in expected:
            if not isinstance(observation, UpstreamObservationV0):
                raise TypeError("Context checks must be UpstreamObservationV0 records.")
            if observation.signal is not signal:
                raise ValueError(f"Expected {signal.value} observation in its context slot.")
            if (
                observation.receipt_id != self.receipt_id
                or observation.field_id != self.field_id
            ):
                raise ValueError("Every upstream observation must match context identity.")
            if (
                observation.provider_id != self.context_builder_id
                or observation.provider_version != self.context_builder_version
            ):
                raise ValueError(
                    "Every upstream observation must match the context builder."
                )
        if self.record_version != SUSPICION_RECORD_VERSION:
            raise ValueError("Unsupported suspicion record version.")

    @property
    def upstream_observations(self) -> tuple[UpstreamObservationV0, ...]:
        return (
            self.required_content,
            self.parse_type,
            self.line_association,
            self.arithmetic,
        )


@dataclass(frozen=True, slots=True)
class SuspicionConfigurationV0:
    """Suspicion subconfiguration traceably owned by one READY Theta_A ref."""

    theta_a_ref: ConfigurationRefV1
    ocr_confidence_rule: ConfidenceRuleV0
    extractor_confidence_rule: ConfidenceRuleV0
    context_builder_id: str
    context_builder_version: str
    record_version: str = SUSPICION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.theta_a_ref, ConfigurationRefV1):
            raise TypeError("theta_a_ref must be ConfigurationRefV1.")
        if self.theta_a_ref.kind is not ConfigurationKind.THETA_A:
            raise ValueError("Suspicion configuration requires THETA_A.")
        if self.theta_a_ref.state is not ConfigurationState.READY:
            raise ValueError("Suspicion configuration requires READY THETA_A.")
        if self.theta_a_ref.content_hash is None:
            raise ValueError("READY THETA_A requires its existing content hash.")
        if not isinstance(self.ocr_confidence_rule, ConfidenceRuleV0):
            raise TypeError("ocr_confidence_rule must be ConfidenceRuleV0.")
        if not isinstance(self.extractor_confidence_rule, ConfidenceRuleV0):
            raise TypeError("extractor_confidence_rule must be ConfidenceRuleV0.")
        if (
            self.ocr_confidence_rule.aggregation
            is not ConfidenceAggregationV0.MIN_ALL_REFERENCED
        ):
            raise ValueError("OCR confidence requires MIN_ALL_REFERENCED aggregation.")
        if (
            self.extractor_confidence_rule.aggregation
            is not ConfidenceAggregationV0.DIRECT
        ):
            raise ValueError("Extractor confidence requires DIRECT aggregation.")
        if self.ocr_confidence_rule.rule_id == self.extractor_confidence_rule.rule_id:
            raise ValueError("OCR and extractor confidence rules require distinct IDs.")
        _require_text(self.context_builder_id, "context_builder_id")
        _require_text(self.context_builder_version, "context_builder_version")
        if self.record_version != SUSPICION_RECORD_VERSION:
            raise ValueError("Unsupported suspicion record version.")


@dataclass(frozen=True, slots=True)
class SuspicionResultV0:
    """Immutable suspicion result with canonical reasons and full provenance."""

    result_id: str
    method_ready_field: MethodReadyFieldV1
    context: SuspicionContextV0
    configuration: SuspicionConfigurationV0
    theta_a_ref: ConfigurationRefV1
    ocr_confidence: ConfidenceObservationV0
    extractor_confidence: ConfidenceObservationV0
    reasons: tuple[SuspicionReasonCode, ...]
    detector_version: str = SUSPICION_DETECTOR_VERSION
    record_version: str = SUSPICION_RECORD_VERSION

    def __post_init__(self) -> None:
        _require_text(self.result_id, "result_id")
        if not isinstance(self.method_ready_field, MethodReadyFieldV1):
            raise TypeError("method_ready_field must be MethodReadyFieldV1.")
        if not isinstance(self.context, SuspicionContextV0):
            raise TypeError("context must be SuspicionContextV0.")
        if not isinstance(self.configuration, SuspicionConfigurationV0):
            raise TypeError("configuration must be SuspicionConfigurationV0.")
        if not isinstance(self.ocr_confidence, ConfidenceObservationV0):
            raise TypeError("ocr_confidence must be ConfidenceObservationV0.")
        if not isinstance(self.extractor_confidence, ConfidenceObservationV0):
            raise TypeError("extractor_confidence must be ConfidenceObservationV0.")
        if self.result_id != _result_id(self.method_ready_field, self.configuration):
            raise ValueError("result_id must be deterministic for the field and Theta_A.")
        if self.theta_a_ref != self.configuration.theta_a_ref:
            raise ValueError("Result must retain the exact Theta_A reference.")
        _validate_identity(self.method_ready_field, self.context, self.configuration)
        expected_ocr = _confidence_observation(
            self.configuration.ocr_confidence_rule,
            tuple(
                (token.token_id, token.raw_confidence)
                for token in self.method_ready_field.source_tokens
            ),
        )
        if self.ocr_confidence != expected_ocr:
            raise ValueError(
                "OCR observation must exactly match original source-token confidence."
            )
        expected_extractor = _confidence_observation(
            self.configuration.extractor_confidence_rule,
            (
                (
                    self.method_ready_field.field_id,
                    self.method_ready_field.original_b2_field.confidence,
                ),
            ),
        )
        if self.extractor_confidence != expected_extractor:
            raise ValueError(
                "Extractor observation must exactly match original B2 confidence."
            )
        expected = _ordered_reasons(
            self.ocr_confidence,
            self.extractor_confidence,
            self.context,
            self.configuration,
        )
        if self.reasons != expected:
            raise ValueError("Suspicion reasons must exactly match canonical signal results.")
        if self.detector_version != SUSPICION_DETECTOR_VERSION:
            raise ValueError("Unsupported suspicion detector version.")
        if self.record_version != SUSPICION_RECORD_VERSION:
            raise ValueError("Unsupported suspicion record version.")

    @property
    def is_suspicious(self) -> bool:
        return bool(self.reasons)

    @property
    def upstream_observations(self) -> tuple[UpstreamObservationV0, ...]:
        return self.context.upstream_observations


def detect_suspicion(
    method_field: MethodReadyFieldV1,
    context: SuspicionContextV0,
    configuration: SuspicionConfigurationV0,
) -> SuspicionResultV0:
    """Evaluate the six permitted upstream suspicion signals deterministically."""

    if not isinstance(method_field, MethodReadyFieldV1):
        raise TypeError("method_field must be MethodReadyFieldV1.")
    if not isinstance(context, SuspicionContextV0):
        raise TypeError("context must be SuspicionContextV0.")
    if not isinstance(configuration, SuspicionConfigurationV0):
        raise TypeError("configuration must be SuspicionConfigurationV0.")

    _validate_identity(method_field, context, configuration)
    ocr_confidence = _confidence_observation(
        configuration.ocr_confidence_rule,
        tuple((token.token_id, token.raw_confidence) for token in method_field.source_tokens),
    )
    extractor_confidence = _confidence_observation(
        configuration.extractor_confidence_rule,
        ((method_field.field_id, method_field.original_b2_field.confidence),),
    )
    reasons = _ordered_reasons(
        ocr_confidence,
        extractor_confidence,
        context,
        configuration,
    )
    return SuspicionResultV0(
        result_id=_result_id(method_field, configuration),
        method_ready_field=method_field,
        context=context,
        configuration=configuration,
        theta_a_ref=configuration.theta_a_ref,
        ocr_confidence=ocr_confidence,
        extractor_confidence=extractor_confidence,
        reasons=reasons,
    )


def _validate_identity(
    method_field: MethodReadyFieldV1,
    context: SuspicionContextV0,
    configuration: SuspicionConfigurationV0,
) -> None:
    original = method_field.original_b2_field
    if original.status is not FieldStatus.EXTRACTED:
        raise SuspicionIntegrityError("Only an EXTRACTED B2 field may be inspected.")
    if (
        original.receipt_id != method_field.receipt_id
        or original.field_id != method_field.field_id
        or original.field_name is not method_field.field_name
    ):
        raise SuspicionIntegrityError("Method-ready and original B2 identities differ.")
    if (
        original.value != method_field.original_value
        or method_field.original_value != method_field.c0_value
    ):
        raise SuspicionIntegrityError("Permanent c0 no longer equals original B2 value.")
    if original.source_token_ids != method_field.source_token_ids:
        raise SuspicionIntegrityError("B2 and method-ready source-token IDs differ.")
    if tuple(token.token_id for token in method_field.source_tokens) != (
        method_field.source_token_ids
    ):
        raise SuspicionIntegrityError("Method-ready source-token order is inconsistent.")
    if any(token.receipt_id != method_field.receipt_id for token in method_field.source_tokens):
        raise SuspicionIntegrityError("A source token belongs to another receipt.")
    gate = method_field.stored_gate_result
    if gate.receipt_id != method_field.receipt_id:
        raise SuspicionIntegrityError("Stored gate and method-ready receipt differ.")
    if gate.decision is not SourceEvidenceDecision.SUFFICIENT:
        raise SuspicionIntegrityError("Suspicion detection requires stored SUFFICIENT gate.")

    expected_context = (
        (context.receipt_id, method_field.receipt_id, "receipt"),
        (context.method_field_id, method_field.method_field_id, "method field"),
        (context.field_id, method_field.field_id, "field"),
        (context.gate_result_id, gate.gate_result_id, "gate result"),
        (context.source_image_id, method_field.source_image_id, "source image"),
        (context.source_token_ids, method_field.source_token_ids, "source tokens"),
    )
    for actual, expected, name in expected_context:
        if actual != expected:
            raise SuspicionIntegrityError(f"Suspicion context {name} identity differs.")
    if (
        context.context_builder_id != configuration.context_builder_id
        or context.context_builder_version != configuration.context_builder_version
    ):
        raise SuspicionIntegrityError("Context builder does not match Theta_A configuration.")
    if context.ocr_confidence_source != configuration.ocr_confidence_rule.score_source:
        raise SuspicionIntegrityError("OCR confidence source does not match configuration.")
    if (
        method_field.b2_extractor_version
        != configuration.extractor_confidence_rule.score_source
    ):
        raise SuspicionIntegrityError(
            "Extractor confidence source does not match the exact B2 version."
        )


def _confidence_observation(
    rule: ConfidenceRuleV0,
    raw_evidence: tuple[tuple[str, object | None], ...],
) -> ConfidenceObservationV0:
    evidence: list[ConfidenceEvidenceV0] = []
    for evidence_id, raw_value in raw_evidence:
        value = None
        if raw_value is not None:
            value = _decimal_from_number(raw_value, evidence_id)
            if not rule.domain_minimum <= value <= rule.domain_maximum:
                raise SuspicionIntegrityError(
                    f"Confidence {evidence_id!r} lies outside its declared domain."
                )
        evidence.append(ConfidenceEvidenceV0(evidence_id=evidence_id, value=value))

    missing = tuple(item.evidence_id for item in evidence if item.value is None)
    if missing:
        availability = ConfidenceAvailabilityV0.UNAVAILABLE
        aggregate = None
    else:
        availability = ConfidenceAvailabilityV0.AVAILABLE
        values = tuple(item.value for item in evidence)
        assert all(value is not None for value in values)
        available_values = tuple(value for value in values if value is not None)
        aggregate = (
            min(available_values)
            if rule.aggregation is ConfidenceAggregationV0.MIN_ALL_REFERENCED
            else available_values[0]
        )
    return ConfidenceObservationV0(
        rule_id=rule.rule_id,
        score_source=rule.score_source,
        aggregation=rule.aggregation,
        availability=availability,
        evidence=tuple(evidence),
        aggregate=aggregate,
        missing_evidence_ids=missing,
    )


def _decimal_from_number(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise SuspicionIntegrityError(f"Confidence {name!r} must be a non-Boolean number.")
    if isinstance(value, float) and not isfinite(value):
        raise SuspicionIntegrityError(f"Confidence {name!r} must be finite.")
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    if not decimal_value.is_finite():
        raise SuspicionIntegrityError(f"Confidence {name!r} must be finite.")
    return decimal_value


def _ordered_reasons(
    ocr: ConfidenceObservationV0,
    extractor: ConfidenceObservationV0,
    context: SuspicionContextV0,
    configuration: SuspicionConfigurationV0,
) -> tuple[SuspicionReasonCode, ...]:
    triggered: set[SuspicionReasonCode] = set()
    if (
        ocr.availability is ConfidenceAvailabilityV0.AVAILABLE
        and ocr.aggregate is not None
        and ocr.aggregate < configuration.ocr_confidence_rule.threshold
    ):
        triggered.add(SuspicionReasonCode.LOW_OCR_CONFIDENCE)
    if (
        extractor.availability is ConfidenceAvailabilityV0.AVAILABLE
        and extractor.aggregate is not None
        and extractor.aggregate < configuration.extractor_confidence_rule.threshold
    ):
        triggered.add(SuspicionReasonCode.LOW_EXTRACTOR_CONFIDENCE)
    for observation in context.upstream_observations:
        if observation.state is UpstreamObservationStateV0.FAIL:
            triggered.add(_SIGNAL_REASON[observation.signal])
    return tuple(reason for reason in SUSPICION_REASON_ORDER if reason in triggered)


def _result_id(
    method_field: MethodReadyFieldV1, configuration: SuspicionConfigurationV0
) -> str:
    theta = configuration.theta_a_ref
    return (
        f"{method_field.method_field_id}:suspicion:"
        f"{theta.configuration_id}:{theta.configuration_version}:v0"
    )
