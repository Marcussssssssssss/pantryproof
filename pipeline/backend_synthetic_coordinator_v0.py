"""Invocation-local synthetic stage ownership over unchanged public components.

The optional declaration never injects a fault. A matching observed exception
and eligible retained records are required before L03 is invoked. Returned
traces are private in-memory evidence, not wire objects or historical execution
authentication. No OCR, operational gate policy, retries or delivery is supplied.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from math import isfinite
import re

from pipeline.contracts import (
    FailureStage, FieldStatus, OcrSourceToken, OutputStage, Point, PolicyState,
    PreResolutionDisposition, ReceiptExtractionStatus, ReceiptFieldName,
    ReceiptItemRow, ReceiptOutput, ReceiptSourceEvidence, SourceEvidenceDecision,
    SourceEvidenceGateResult, SourceProcessingStatus, SourceProvenance, StructuredField,
)
from pipeline.layout_b2 import B2ExtractionResult, extract_b2
from pipeline.ocr_adapter import AdaptedOcrSource, attach_gate_result
from pipeline.presentation_v1.b2_synthetic_projection_v0 import project_retained_b2_fixture_presentation_v1
from pipeline.presentation_v1.conformance import decode_and_validate_presentation_v1
from pipeline.presentation_v1.synthetic_failure_projection_v0 import (
    NoFailureEnvelopeReasonV0, NoFailureEnvelopeV0, SyntheticDeferredEventV0,
    SyntheticFailureCaseV0, SyntheticFailureContextV0, SyntheticFailureFactsV0,
    ValidatedFailureEnvelopeV0, build_synthetic_failure_presentation_v1,
)

__all__ = (
    "SyntheticExecutionTraceV0", "SyntheticCoordinatorResultV0",
    "SyntheticCoordinatorRejectionV0", "SyntheticCoordinatorRejectionReasonV0",
    "coordinate_synthetic_receipt_v0",
)


class SyntheticCoordinatorRejectionReasonV0(Enum):
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_GATE_RESULT = "INVALID_GATE_RESULT"
    ATTACHMENT_REJECTED = "ATTACHMENT_REJECTED"
    INVALID_B2_RESULT = "INVALID_B2_RESULT"
    GATE_EXCEPTION = "GATE_EXCEPTION"
    B2_EXCEPTION = "B2_EXCEPTION"
    PROJECTION_REJECTED = "PROJECTION_REJECTED"
    SYNTHETIC_EVENT_NOT_OBSERVED = "SYNTHETIC_EVENT_NOT_OBSERVED"
    COORDINATOR_FAILED = "COORDINATOR_FAILED"


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticExecutionTraceV0:
    adapted_source: AdaptedOcrSource | None
    gate_result: SourceEvidenceGateResult | None
    source_evidence: ReceiptSourceEvidence | None
    b2_result: B2ExtractionResult | None


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticCoordinatorRejectionV0:
    reason: SyntheticCoordinatorRejectionReasonV0


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticCoordinatorResultV0:
    trace: SyntheticExecutionTraceV0
    result: bytes | NoFailureEnvelopeV0 | SyntheticCoordinatorRejectionV0


_Reason = SyntheticCoordinatorRejectionReasonV0
_Case = SyntheticFailureCaseV0
_Deferred = SyntheticDeferredEventV0.POST_INSUFFICIENT_PRESENTATION_EXCEPTION
_DECLARATIONS = (
    _Case.SOURCE_GATE_EXECUTION_FAILURE, _Case.EXTRACTION_ENGINE_FAILURE,
    _Case.PRESENTATION_PROJECTION_FAILURE, _Deferred, None,
)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_PRIVATE_ID = re.compile(
    r"(?:\A|[._-])(?:participant|evaluation|ground[-_]?truth|annotation|held[-_]?out)"
    r"(?:\Z|[._-])", re.IGNORECASE | re.ASCII,
)
_NAMESPACE = re.compile(r"[0-9a-f]{32}")

# Closed, trusted schemas: tuples denote unions, lists denote exact tuples.
# No caller-supplied descriptor, property, mapping, repr or coercion is used.
_SHAPES = {
    SyntheticFailureContextV0: dict.fromkeys(("request_id", "image_id", "alias_namespace", "consumer_mode"), str),
    AdaptedOcrSource: {
        "receipt_id": str, "image_id": str, "provenance": SourceProvenance,
        "processing_status": SourceProcessingStatus, "tokens": [OcrSourceToken],
    },
    SourceProvenance: {"source_system": str, "source_reference": str, "content_sha256": (str, type(None))},
    Point: {"x": (int, float), "y": (int, float)},
    OcrSourceToken: {
        "receipt_id": str, "token_id": str, "original_text": str, "polygon": [Point],
        "raw_confidence": (int, float, type(None)),
    },
    SourceEvidenceGateResult: {
        "gate_result_id": str, "receipt_id": str, "decision": SourceEvidenceDecision, "reasons": [str],
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
_ENUMS = {cls: tuple(cls) for cls in (
    SourceProcessingStatus, SourceEvidenceDecision, PolicyState, FailureStage,
    ReceiptExtractionStatus, OutputStage, ReceiptFieldName, FieldStatus,
)}


def _shape(value: object, specification: object) -> bool:
    if type(specification) is tuple:
        return any(_shape(value, option) for option in specification)
    if type(specification) is list:
        return type(value) is tuple and all(_shape(item, specification[0]) for item in value)
    if type(value) is not specification:
        return False
    if specification in _ENUMS:
        return any(value is member for member in _ENUMS[specification])
    if specification in _SHAPES:
        for name, member_shape in _SHAPES[specification].items():
            try:
                member = object.__getattribute__(value, name)
            except AttributeError:
                return False
            if not _shape(member, member_shape):
                return False
    return True


def _revalidate(value: object) -> None:
    cls = type(value)
    if cls is tuple:
        for item in value:
            _revalidate(item)
    elif cls in _SHAPES:
        for name in _SHAPES[cls]:
            _revalidate(object.__getattribute__(value, name))
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
        # Point is a passive record; it has no __post_init__ validator.
        if cls is not Point:
            cls.__post_init__(value)


def _record_valid(value: object, cls: type) -> bool:
    if not _shape(value, cls):
        return False
    try:
        _revalidate(value)
    except ValueError:
        return False
    return True


def _protocol_id(value: object) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None and _PRIVATE_ID.search(value) is None


def _input_valid(source, evaluator, context, producer, declaration) -> bool:
    return (
        _shape(context, SyntheticFailureContextV0)
        and context.consumer_mode == "FIXTURE"
        and all(_protocol_id(value) for value in (context.request_id, context.image_id, producer))
        and _NAMESPACE.fullmatch(context.alias_namespace) is not None
        and any(declaration is member for member in _DECLARATIONS)
        and callable(evaluator)
        and _shape(source, AdaptedOcrSource)
    )


def _evidence_matches(source, gate, evidence) -> bool:
    return (
        _record_valid(source, AdaptedOcrSource)
        and _record_valid(gate, SourceEvidenceGateResult)
        and _record_valid(evidence, ReceiptSourceEvidence)
        and evidence.receipt_id == source.receipt_id == gate.receipt_id
        and evidence.image_id == source.image_id
        and evidence.processing_status is source.processing_status
        and evidence.tokens is source.tokens and evidence.provenance is source.provenance
        and evidence.gate_result is gate
    )


def _result_matches(source, gate, evidence, result) -> bool:
    if not _evidence_matches(source, gate, evidence) or not _record_valid(result, B2ExtractionResult):
        return False
    output = result.receipt_output
    if output is None:
        return (
            gate.decision is SourceEvidenceDecision.INSUFFICIENT
            and result.pre_resolution_disposition.state is PolicyState.FALLBACK_NO_UPDATE
            and result.pre_resolution_disposition.gate_result is gate
        )
    return (
        gate.decision is SourceEvidenceDecision.SUFFICIENT
        and output.source_evidence is evidence and output.receipt_id == source.receipt_id
        and output.output_stage is OutputStage.PRE_REVIEW_AUTOMATIC
    )


def _call(operation, *args, **kwargs):
    """Forget the exception before returning; never inspect its metadata."""
    try:
        value = operation(*args, **kwargs)
    except Exception as error:
        cls = type(error)
        validation = issubclass(cls, (ValueError, TypeError))
        # S01 publishes ValueError/ConformanceViolation and RuntimeError as safe
        # rejection surfaces. Their hidden causes cannot be inferred here.
        projection_rejection = issubclass(cls, (ValueError, TypeError, RuntimeError))
        return False, None, validation, projection_rejection
    return True, value, False, False


def _failure_result(context, declaration, state, fallback):
    source, gate, evidence, result = state
    if not _record_valid(source, AdaptedOcrSource):
        return fallback
    completed = source.processing_status in (SourceProcessingStatus.OCR_COMPLETED, SourceProcessingStatus.OCR_PARTIAL)
    if declaration is _Case.SOURCE_GATE_EXECUTION_FAILURE:
        eligible = completed and gate is evidence is result is None
    elif declaration is _Case.EXTRACTION_ENGINE_FAILURE:
        eligible = (completed and _evidence_matches(source, gate, evidence)
                    and gate.decision is SourceEvidenceDecision.SUFFICIENT and result is None)
    else:
        eligible = _result_matches(source, gate, evidence, result)
        if declaration is _Deferred:
            eligible = eligible and gate.decision is SourceEvidenceDecision.INSUFFICIENT
        else:
            eligible = eligible and completed and gate.decision is SourceEvidenceDecision.SUFFICIENT
    if not eligible:
        return fallback
    classified = build_synthetic_failure_presentation_v1(
        context=context,
        failure=SyntheticFailureFactsV0(
            context.request_id, context.image_id, declaration, source, gate, evidence, result,
        ),
    )
    if type(classified) is ValidatedFailureEnvelopeV0 and type(classified.payload) is bytes:
        if declaration is _Deferred:
            return _Reason.COORDINATOR_FAILED
        valid, dto, _, _ = _call(
            decode_and_validate_presentation_v1, classified.payload,
            expected_request_id=context.request_id, expected_image_id=context.image_id,
            consumer_mode="FIXTURE",
        )
        if not valid or dto.outcome.status != "PROCESSING_FAILED":
            return _Reason.COORDINATOR_FAILED
        stage = {
            _Case.SOURCE_GATE_EXECUTION_FAILURE: "SOURCE_GATE",
            _Case.EXTRACTION_ENGINE_FAILURE: "EXTRACTION",
            _Case.PRESENTATION_PROJECTION_FAILURE: "PRESENTATION_ADAPTER",
        }[declaration]
        if (dto.outcome.failure.stage, dto.outcome.failure.code, dto.outcome.failure.retryable) != (
            stage, declaration.value, True,
        ):
            return _Reason.COORDINATOR_FAILED
        return classified.payload
    if (type(classified) is NoFailureEnvelopeV0
            and type(classified.reason) is NoFailureEnvelopeReasonV0
            and any(classified.reason is member for member in NoFailureEnvelopeReasonV0)):
        return classified
    return _Reason.COORDINATOR_FAILED


def _execute(source, evaluator, context, producer, declaration, state):
    if not _input_valid(source, evaluator, context, producer, declaration):
        return _Reason.INVALID_INPUT
    state[0] = source
    if not _record_valid(source, AdaptedOcrSource) or source.image_id != context.image_id:
        return _Reason.INVALID_INPUT

    ok, gate, validation, _ = _call(evaluator, source)
    if not ok:
        if declaration is _Case.SOURCE_GATE_EXECUTION_FAILURE and not validation:
            return _failure_result(context, declaration, state, _Reason.GATE_EXCEPTION)
        return _Reason.GATE_EXCEPTION
    if not _shape(gate, SourceEvidenceGateResult):
        return _Reason.INVALID_GATE_RESULT
    state[1] = gate
    if (not _record_valid(source, AdaptedOcrSource) or not _record_valid(gate, SourceEvidenceGateResult)
            or gate.receipt_id != source.receipt_id or source.image_id != context.image_id):
        return _Reason.INVALID_GATE_RESULT
    if declaration is _Case.SOURCE_GATE_EXECUTION_FAILURE:
        return _Reason.SYNTHETIC_EVENT_NOT_OBSERVED

    ok, evidence, _, _ = _call(attach_gate_result, source, gate)
    if not ok:
        return _Reason.ATTACHMENT_REJECTED
    if not _shape(evidence, ReceiptSourceEvidence):
        return _Reason.ATTACHMENT_REJECTED
    state[2] = evidence
    if not _evidence_matches(source, gate, evidence):
        return _Reason.ATTACHMENT_REJECTED

    ok, result, validation, _ = _call(extract_b2, evidence)
    if not ok:
        if declaration is _Case.EXTRACTION_ENGINE_FAILURE and not validation:
            return _failure_result(context, declaration, state, _Reason.B2_EXCEPTION)
        return _Reason.B2_EXCEPTION
    if not _shape(result, B2ExtractionResult):
        return _Reason.INVALID_B2_RESULT
    state[3] = result
    if not _result_matches(source, gate, evidence, result):
        return _Reason.INVALID_B2_RESULT
    if declaration is _Case.EXTRACTION_ENGINE_FAILURE:
        return _Reason.SYNTHETIC_EVENT_NOT_OBSERVED

    ok, raw, _, projection_rejection = _call(
        project_retained_b2_fixture_presentation_v1,
        adapted_source=source, source_evidence=evidence, b2_result=result,
        request_id=context.request_id, image_id=context.image_id,
        alias_namespace=context.alias_namespace, producer_id=producer, consumer_mode="FIXTURE",
    )
    if not ok:
        if declaration in (_Case.PRESENTATION_PROJECTION_FAILURE, _Deferred) and not projection_rejection:
            return _failure_result(context, declaration, state, _Reason.PROJECTION_REJECTED)
        return _Reason.PROJECTION_REJECTED
    if type(raw) is not bytes:
        return _Reason.PROJECTION_REJECTED
    valid, dto, validation, _ = _call(
        decode_and_validate_presentation_v1, raw, expected_request_id=context.request_id,
        expected_image_id=context.image_id, consumer_mode="FIXTURE",
    )
    if not valid:
        return _Reason.PROJECTION_REJECTED if validation else _Reason.COORDINATOR_FAILED
    expected = "RESULT_AVAILABLE" if gate.decision is SourceEvidenceDecision.SUFFICIENT else "SOURCE_EVIDENCE_INSUFFICIENT"
    if dto.outcome.status != expected:
        return _Reason.PROJECTION_REJECTED
    if declaration is not None:
        return _Reason.SYNTHETIC_EVENT_NOT_OBSERVED
    return raw


def coordinate_synthetic_receipt_v0(
    *,
    adapted_source: AdaptedOcrSource,
    gate_evaluator: Callable[[AdaptedOcrSource], SourceEvidenceGateResult],
    context: SyntheticFailureContextV0,
    producer_id: str,
    expected_synthetic_failure: SyntheticFailureCaseV0 | SyntheticDeferredEventV0 | None = None,
) -> SyntheticCoordinatorResultV0:
    """Own one synthetic invocation and return validated bytes or a local result.

    A declaration never causes an exception. Known validation failures remain
    local even with a declaration. Controlled technical projection tests must
    use an unexpected boundary fault outside S01's sanitized rejection family;
    a sanitized RuntimeError cannot authenticate its hidden cause.
    """
    state = [None, None, None, None]
    try:
        result = _execute(adapted_source, gate_evaluator, context, producer_id, expected_synthetic_failure, state)
    except Exception:
        result = _Reason.COORDINATOR_FAILED
    # No original exception, diagnostic or callback is retained or run here.
    # Only local record construction occurs after a selected result.
    if type(result) is _Reason:
        result = SyntheticCoordinatorRejectionV0(result)
    return SyntheticCoordinatorResultV0(SyntheticExecutionTraceV0(*state), result)
