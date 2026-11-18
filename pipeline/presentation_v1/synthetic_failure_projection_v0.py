"""Synthetic-only projection of retained stage facts into V1 failure bytes.

This boundary performs no upstream execution, delivery, retry or cancellation.
It checks supplied record relationships, not historical exception authenticity.
The deferred event and all rejection results remain local Python classifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from math import isfinite
import re

from pipeline.contracts import (
    CONTRACT_VERSION,
    FailureStage,
    FieldStatus,
    OcrSourceToken,
    OutputStage,
    Point,
    PolicyState,
    PreResolutionDisposition,
    ReceiptExtractionStatus,
    ReceiptFieldName,
    ReceiptItemRow,
    ReceiptOutput,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
    StructuredField,
)
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.ocr_adapter import AdaptedOcrSource
from pipeline.presentation_v1.conformance import (
    ConformanceViolation,
    decode_and_validate_presentation_v1,
)

__all__ = (
    "SyntheticFailureCaseV0", "SyntheticDeferredEventV0", "NoFailureEnvelopeReasonV0",
    "SyntheticFailureContextV0", "SyntheticFailureFactsV0", "ValidatedFailureEnvelopeV0",
    "NoFailureEnvelopeV0", "build_synthetic_failure_presentation_v1",
)


class SyntheticFailureCaseV0(Enum):
    PROCESSOR_NOT_AVAILABLE = "PROCESSOR_NOT_AVAILABLE"
    OCR_ENGINE_FAILURE = "OCR_ENGINE_FAILURE"
    SOURCE_GATE_EXECUTION_FAILURE = "SOURCE_GATE_EXECUTION_FAILURE"
    EXTRACTION_ENGINE_FAILURE = "EXTRACTION_ENGINE_FAILURE"
    PRESENTATION_PROJECTION_FAILURE = "PRESENTATION_PROJECTION_FAILURE"


class SyntheticDeferredEventV0(Enum):
    POST_INSUFFICIENT_PRESENTATION_EXCEPTION = "POST_INSUFFICIENT_PRESENTATION_EXCEPTION"


class NoFailureEnvelopeReasonV0(Enum):
    INVALID_INPUT = "INVALID_INPUT"
    CORRELATION_MISMATCH = "CORRELATION_MISMATCH"
    INVALID_ASSOCIATION = "INVALID_ASSOCIATION"
    DEFERRED_POST_INSUFFICIENT = "DEFERRED_POST_INSUFFICIENT"
    STAGE_NOT_REPRESENTABLE = "STAGE_NOT_REPRESENTABLE"
    V1_VALIDATION_REJECTED = "V1_VALIDATION_REJECTED"
    UNSAFE_GATE_REASON = "UNSAFE_GATE_REASON"
    EMISSION_FAILED = "EMISSION_FAILED"


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticFailureContextV0:
    request_id: str
    image_id: str
    alias_namespace: str
    consumer_mode: str


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticFailureFactsV0:
    request_id: str
    image_id: str
    case: SyntheticFailureCaseV0 | SyntheticDeferredEventV0
    adapted_source: AdaptedOcrSource | None
    gate_result: SourceEvidenceGateResult | None
    source_evidence: ReceiptSourceEvidence | None
    b2_result: B2ExtractionResult | None


@dataclass(frozen=True, slots=True, repr=False)
class ValidatedFailureEnvelopeV0:
    payload: bytes


@dataclass(frozen=True, slots=True, repr=False)
class NoFailureEnvelopeV0:
    reason: NoFailureEnvelopeReasonV0


_CASE = SyntheticFailureCaseV0
_REASON = NoFailureEnvelopeReasonV0
_CATALOGUE = {
    _CASE.PROCESSOR_NOT_AVAILABLE: ("AVAILABILITY", "PROCESSOR_NOT_AVAILABLE", False),
    _CASE.OCR_ENGINE_FAILURE: ("OCR", "OCR_ENGINE_FAILURE", True),
    _CASE.SOURCE_GATE_EXECUTION_FAILURE: ("SOURCE_GATE", "SOURCE_GATE_EXECUTION_FAILURE", True),
    _CASE.EXTRACTION_ENGINE_FAILURE: ("EXTRACTION", "EXTRACTION_ENGINE_FAILURE", True),
    _CASE.PRESENTATION_PROJECTION_FAILURE: ("PRESENTATION_ADAPTER", "PRESENTATION_PROJECTION_FAILURE", True),
}
_PROTOCOL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_NAMESPACE = re.compile(r"[0-9a-f]{32}")
_PRIVATE_ID = re.compile(
    r"(?:\A|[._-])(?:participant|evaluation|ground[-_]?truth|annotation|held[-_]?out)"
    r"(?:\Z|[._-])", re.IGNORECASE | re.ASCII,
)
_GATE_REASONS = frozenset((
    "Synthetic source structure was unavailable.",
    "There is 1 unreadable row.",
    "The x marker was unavailable.",
    "Extraction could not locate 1 safe heading.",
))

# Closed record schemas. A list means an exact tuple of elements; a tuple
# means an exact-type union. These specifications are never input supplied.
_RECORD_SHAPES = {
    SyntheticFailureContextV0: {
        "request_id": str, "image_id": str, "alias_namespace": str, "consumer_mode": str,
    },
    SyntheticFailureFactsV0: {
        "request_id": str, "image_id": str,
        "case": (SyntheticFailureCaseV0, SyntheticDeferredEventV0),
        "adapted_source": (AdaptedOcrSource, type(None)),
        "gate_result": (SourceEvidenceGateResult, type(None)),
        "source_evidence": (ReceiptSourceEvidence, type(None)),
        "b2_result": (B2ExtractionResult, type(None)),
    },
    AdaptedOcrSource: {
        "receipt_id": str, "image_id": str, "provenance": SourceProvenance,
        "processing_status": SourceProcessingStatus, "tokens": [OcrSourceToken],
    },
    SourceProvenance: {
        "source_system": str, "source_reference": str, "content_sha256": (str, type(None)),
    },
    Point: {"x": (int, float), "y": (int, float)},
    OcrSourceToken: {
        "receipt_id": str, "token_id": str, "original_text": str,
        "polygon": [Point], "raw_confidence": (int, float, type(None)),
    },
    SourceEvidenceGateResult: {
        "gate_result_id": str, "receipt_id": str, "decision": SourceEvidenceDecision,
        "reasons": [str],
    },
    ReceiptSourceEvidence: {
        "receipt_id": str, "image_id": str, "provenance": SourceProvenance,
        "processing_status": SourceProcessingStatus, "tokens": [OcrSourceToken],
        "gate_result": SourceEvidenceGateResult,
    },
    B2ExtractionResult: {
        "receipt_output": (ReceiptOutput, type(None)),
        "pre_resolution_disposition": (PreResolutionDisposition, type(None)),
    },
    PreResolutionDisposition: {
        "state": PolicyState, "gate_result": SourceEvidenceGateResult,
        "failure_stage": (FailureStage, type(None)), "failure_reason": (str, type(None)),
    },
    ReceiptOutput: {
        "receipt_id": str, "store_name": StructuredField, "purchase_date": StructuredField,
        "items": [ReceiptItemRow], "receipt_total": StructuredField,
        "source_evidence": ReceiptSourceEvidence, "extraction_status": ReceiptExtractionStatus,
        "extractor_version": str, "output_stage": OutputStage, "contract_version": str,
    },
    ReceiptItemRow: {
        "row_id": str, "receipt_id": str, "description": StructuredField,
        "quantity": StructuredField, "unit_price": StructuredField, "line_total": StructuredField,
        "pantry_product_identity": (str, type(None)),
    },
    StructuredField: {
        "field_id": str, "receipt_id": str, "field_name": ReceiptFieldName, "status": FieldStatus,
        "value": (str, type(None)), "item_row_id": (str, type(None)), "source_token_ids": [str],
        "confidence": (int, float, type(None)), "unresolved_reason": (str, type(None)),
    },
}
_ENUM_MEMBERS = {cls: tuple(cls) for cls in (
    SyntheticFailureCaseV0, SyntheticDeferredEventV0, SourceProcessingStatus,
    SourceEvidenceDecision, PolicyState, FailureStage, ReceiptExtractionStatus,
    OutputStage, ReceiptFieldName, FieldStatus,
)}


def _has_shape(value: object, specification: object) -> bool:
    if type(specification) is tuple:
        return any(_has_shape(value, option) for option in specification)
    if type(specification) is list:
        return type(value) is tuple and all(_has_shape(item, specification[0]) for item in value)
    if type(value) is not specification:
        return False
    if specification in _ENUM_MEMBERS:
        return any(value is member for member in _ENUM_MEMBERS[specification])
    if specification in _RECORD_SHAPES:
        for name, member_shape in _RECORD_SHAPES[specification].items():
            try:
                member = object.__getattribute__(value, name)
            except AttributeError:
                return False
            if not _has_shape(member, member_shape):
                return False
    return True


def _protocol_id_valid(value: str) -> bool:
    return _PROTOCOL_ID.fullmatch(value) is not None and _PRIVATE_ID.search(value) is None


def _inputs_valid(context: object, failure: object) -> bool:
    if not _has_shape(context, SyntheticFailureContextV0) or not _has_shape(failure, SyntheticFailureFactsV0):
        return False
    return (
        context.consumer_mode == "FIXTURE"
        and _NAMESPACE.fullmatch(context.alias_namespace) is not None
        and all(_protocol_id_valid(value) for value in (
            context.request_id, context.image_id, failure.request_id, failure.image_id,
        ))
    )


def _correlated(context: SyntheticFailureContextV0, failure: SyntheticFailureFactsV0) -> bool:
    if context.request_id != failure.request_id or context.image_id != failure.image_id:
        return False
    return all(source is None or source.image_id == context.image_id for source in (
        failure.adapted_source, failure.source_evidence,
    ))


def _revalidate_tree(value: object) -> None:
    cls = type(value)
    if cls is tuple:
        for item in value:
            _revalidate_tree(item)
    elif cls in _RECORD_SHAPES:
        for name in _RECORD_SHAPES[cls]:
            _revalidate_tree(object.__getattribute__(value, name))
        # Type admission precedes all record methods and finite-number checks.
        numbers = ()
        if cls is Point:
            numbers = (value.x, value.y)
        elif cls is OcrSourceToken:
            numbers = (value.raw_confidence,)
        elif cls is StructuredField:
            numbers = (value.confidence,)
        try:
            if any(number is not None and not isfinite(number) for number in numbers):
                raise ValueError("Invalid synthetic record.")
        except OverflowError:
            raise ValueError("Invalid synthetic record.") from None
        # Point is a passive public coordinate record, without a validator.
        # Its exact numeric shape and finiteness were checked above.
        if cls is not Point:
            cls.__post_init__(value)


def _associations_valid(failure: SyntheticFailureFactsV0) -> bool:
    source, gate, evidence, result = (
        failure.adapted_source, failure.gate_result, failure.source_evidence, failure.b2_result,
    )
    try:
        for record in (source, gate, evidence, result):
            _revalidate_tree(record)
        if gate is not None and (source is None or gate.receipt_id != source.receipt_id):
            return False
        if evidence is not None:
            if source is None or gate is None:
                return False
            if (evidence.receipt_id != source.receipt_id or evidence.image_id != source.image_id
                    or evidence.processing_status is not source.processing_status
                    or evidence.tokens is not source.tokens or evidence.provenance is not source.provenance
                    or evidence.gate_result is not gate):
                return False
        if result is not None:
            if evidence is None:
                return False
            if result.receipt_output is not None:
                output = result.receipt_output
                if (output.source_evidence is not evidence or output.receipt_id != evidence.receipt_id
                        or output.output_stage is not OutputStage.PRE_REVIEW_AUTOMATIC):
                    return False
            elif (result.pre_resolution_disposition.gate_result is not gate
                  or gate.decision is not SourceEvidenceDecision.INSUFFICIENT):
                return False
        return True
    except ValueError:
        return False


def _valid_deferred_event(failure: SyntheticFailureFactsV0) -> bool:
    return (
        failure.case is SyntheticDeferredEventV0.POST_INSUFFICIENT_PRESENTATION_EXCEPTION
        and failure.adapted_source is not None
        and failure.source_evidence is not None
        and failure.gate_result is not None
        and failure.gate_result.decision is SourceEvidenceDecision.INSUFFICIENT
        and (failure.b2_result is None or failure.b2_result.receipt_output is None)
    )


def _stage_representable(failure: SyntheticFailureFactsV0) -> bool:
    if type(failure.case) is not SyntheticFailureCaseV0:
        return False
    source, gate, evidence, result = (
        failure.adapted_source, failure.gate_result, failure.source_evidence, failure.b2_result,
    )
    if failure.case is _CASE.PROCESSOR_NOT_AVAILABLE:
        return source is gate is evidence is result is None
    if failure.case is _CASE.OCR_ENGINE_FAILURE:
        return (source is None or source.processing_status is SourceProcessingStatus.OCR_FAILED) and gate is evidence is result is None
    if source is None or source.processing_status not in (
        SourceProcessingStatus.OCR_COMPLETED, SourceProcessingStatus.OCR_PARTIAL,
    ):
        return False
    if failure.case is _CASE.SOURCE_GATE_EXECUTION_FAILURE:
        return gate is evidence is result is None
    if gate is None or gate.decision is not SourceEvidenceDecision.SUFFICIENT or evidence is None:
        return False
    if failure.case is _CASE.EXTRACTION_ENGINE_FAILURE:
        return result is None
    return result is not None and result.receipt_output is not None


def _envelope(context: SyntheticFailureContextV0, failure: SyntheticFailureFactsV0) -> dict:
    stage, code, retryable = _CATALOGUE[failure.case]
    source, gate = failure.adapted_source, failure.gate_result
    namespace = context.alias_namespace
    return {
        "schemaName": "receipt-presentation", "schemaVersion": "1", "sourceContractVersion": CONTRACT_VERSION,
        "requestId": context.request_id, "imageId": context.image_id,
        "source": {"type": "SYNTHETIC_FIXTURE", "provenance": {
            "sourceSystem": "I2B_SYNTHETIC_FAILURE_V0", "sourceReference": f"src-v1-{namespace}-1",
            "contentSha256": None,
        }},
        "outcome": {
            "status": "PROCESSING_UNAVAILABLE" if stage == "AVAILABILITY" else "PROCESSING_FAILED",
            "failure": {"stage": stage, "code": code, "retryable": retryable},
        },
        "sourceEvidence": None if source is None else {
            "sourceProcessingStatus": source.processing_status.value,
            "tokenIds": [f"tok-v1-{namespace}-{index}" for index, _ in enumerate(source.tokens, 1)],
        },
        "sourceGate": None if gate is None else {
            "gateResultId": f"gat-v1-{namespace}-1", "decision": gate.decision.value,
            "reasons": list(gate.reasons),
        },
        "automaticExtraction": None, "receipt": None,
    }


def _serialize(envelope: dict) -> bytes:
    return json.dumps(
        envelope, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"),
    ).encode("utf-8")


def _gate_reasons_safe(failure: SyntheticFailureFactsV0) -> bool:
    if failure.gate_result is None:
        return True
    transcriptions = frozenset(token.original_text for token in failure.adapted_source.tokens)
    return all(reason in _GATE_REASONS and reason not in transcriptions for reason in failure.gate_result.reasons)


def build_synthetic_failure_presentation_v1(
    *,
    context: SyntheticFailureContextV0,
    failure: SyntheticFailureFactsV0,
) -> ValidatedFailureEnvelopeV0 | NoFailureEnvelopeV0:
    """Project retained synthetic facts; decline at the first applicable check.

    No caller-supplied exception metadata is read or retained. Safe result
    construction occurs outside handlers, and BaseException is not intercepted.
    """
    reason = None
    payload = None
    try:
        if not _inputs_valid(context, failure):
            reason = _REASON.INVALID_INPUT
        elif not _correlated(context, failure):
            reason = _REASON.CORRELATION_MISMATCH
        elif not _associations_valid(failure):
            reason = _REASON.INVALID_ASSOCIATION
        elif _valid_deferred_event(failure):
            reason = _REASON.DEFERRED_POST_INSUFFICIENT
        elif not _stage_representable(failure):
            reason = _REASON.STAGE_NOT_REPRESENTABLE
        else:
            payload = _serialize(_envelope(context, failure))
            try:
                decode_and_validate_presentation_v1(
                    payload, expected_request_id=context.request_id,
                    expected_image_id=context.image_id, consumer_mode="FIXTURE",
                )
            except ConformanceViolation:
                reason = _REASON.V1_VALIDATION_REJECTED
            if reason is None and not _gate_reasons_safe(failure):
                reason = _REASON.UNSAFE_GATE_REASON
    except Exception:
        if reason is None:
            reason = _REASON.EMISSION_FAILED
    if reason is not None:
        return NoFailureEnvelopeV0(reason)
    return ValidatedFailureEnvelopeV0(payload)
