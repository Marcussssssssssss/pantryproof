"""Project a trusted service's retained Android attempt to LOCAL_IMAGE V1.

The service owns the independently recorded request context, opaque aliases,
and LIVE gate authorization. This module performs no OCR, extraction, gate
execution, or operational authorization.
"""

from dataclasses import dataclass, replace
from enum import Enum
import json
import re
from typing import TYPE_CHECKING

from pipeline.contracts import (
    CONTRACT_VERSION,
    OcrSourceToken,
    ReceiptOutput,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
)
from pipeline.gate_c_source_gate_v0 import GATE_C_SOURCE_GATE_V0
from pipeline.layout_b2 import B2ExtractionResult, EXTRACTOR_VERSION
from pipeline.ocr_adapter import AdaptedOcrSource
from pipeline.presentation_v1.b2_synthetic_projection_v0 import (
    _aliases,
    _field_object,
    _protocol_id,
    _validate_result,
    _validate_source,
)
from pipeline.presentation_v1.conformance import decode_and_validate_presentation_v1

if TYPE_CHECKING:
    from pipeline.proposed.purchase_date_correction_v0 import PurchaseDateCorrectionResultV0
    from pipeline.proposed.receipt_research_v1 import ProposedReceiptResearchResult


LOCAL_IMAGE_SOURCE_SYSTEM = "ANDROID_LOCAL_IMAGE"
PROPOSED_UNVERIFIED_PRODUCER = "PROPOSED_UNVERIFIED_REVIEW_V1"
PROPOSED_POLICY_PRODUCER = "PROPOSED_RECEIPT_V1"
_NAMESPACE = re.compile(r"[0-9a-f]{32}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_GENERATED_GATE_REASONS = frozenset(reason for _, reason in GATE_C_SOURCE_GATE_V0.reason_map)


class LocalImageProjectionError(ValueError):
    """A safe refusal to publish a LOCAL_IMAGE envelope."""


class LocalImageFailureV0(Enum):
    PROCESSOR_NOT_AVAILABLE = ("AVAILABILITY", "PROCESSOR_NOT_AVAILABLE", False)
    OCR_ENGINE_FAILURE = ("OCR", "OCR_ENGINE_FAILURE", True)
    SOURCE_GATE_EXECUTION_FAILURE = ("SOURCE_GATE", "SOURCE_GATE_EXECUTION_FAILURE", True)
    EXTRACTION_ENGINE_FAILURE = ("EXTRACTION", "EXTRACTION_ENGINE_FAILURE", True)
    PRESENTATION_PROJECTION_FAILURE = ("PRESENTATION_ADAPTER", "PRESENTATION_PROJECTION_FAILURE", True)


@dataclass(frozen=True, slots=True, repr=False)
class LiveGateApprovalV0:
    """Trusted service configuration for a separately approved LIVE policy."""

    policy_id: str
    revision: str
    policy_sha256: str
    public_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class RetainedLiveGateV0:
    """Exact policy and source references retained when the gate ran."""

    policy: LiveGateApprovalV0
    adapted_source: AdaptedOcrSource
    result: SourceEvidenceGateResult


@dataclass(frozen=True, slots=True, repr=False)
class LocalImagePresentationContextV0:
    """Service-owned identity reserved independently of the terminal attempt."""

    request_id: str
    image_id: str
    receipt_id: str
    alias_namespace: str
    approved_gate: LiveGateApprovalV0 | None = None

    @property
    def source_reference(self) -> str:
        """Pass this opaque reference to the existing OCR adapter."""
        return f"src-v1-{self.alias_namespace}-1"


@dataclass(frozen=True, slots=True, repr=False)
class RetainedLocalImageAttemptV0:
    """Actual stage records for one attempt, retained by the trusted service."""

    request_id: str
    image_id: str
    adapted_source: AdaptedOcrSource | None = None
    gate: RetainedLiveGateV0 | None = None
    source_evidence: ReceiptSourceEvidence | None = None
    b2_result: B2ExtractionResult | None = None
    failure: LocalImageFailureV0 | None = None
    correction: "PurchaseDateCorrectionResultV0 | None" = None
    proposed: "ProposedReceiptResearchResult | None" = None
    proposed_failure: str | None = None
    refusal_code: str | None = None
    image_dimensions: tuple[int, int] | None = None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LocalImageProjectionError(message)


def _validate_attempt(
    context: LocalImagePresentationContextV0, attempt: RetainedLocalImageAttemptV0,
) -> None:
    _require(type(context) is LocalImagePresentationContextV0, "Invalid local-image context.")
    _require(type(attempt) is RetainedLocalImageAttemptV0, "Invalid retained attempt.")
    for identity in (context.request_id, context.image_id, context.receipt_id,
                     attempt.request_id, attempt.image_id):
        _protocol_id(identity)
    _require(
        (attempt.request_id, attempt.image_id) == (context.request_id, context.image_id),
        "Retained request or image does not match the reserved context.",
    )
    _require(
        type(context.alias_namespace) is str and _NAMESPACE.fullmatch(context.alias_namespace) is not None,
        "Invalid local-image alias namespace.",
    )

    adapted = attempt.adapted_source
    if adapted is not None:
        _require(
            type(adapted) is AdaptedOcrSource
            and (adapted.receipt_id, adapted.image_id) == (context.receipt_id, context.image_id)
            and adapted.provenance.source_system == LOCAL_IMAGE_SOURCE_SYSTEM
            and adapted.provenance.source_reference == context.source_reference,
            "Retained OCR does not match the Android local-image source.",
        )
        _require(
            type(adapted.processing_status) is SourceProcessingStatus
            and type(adapted.tokens) is tuple,
            "Invalid retained OCR evidence.",
        )
        for token in adapted.tokens:
            _require(type(token) is OcrSourceToken, "Invalid retained OCR token.")
            OcrSourceToken.__post_init__(token)
        AdaptedOcrSource.__post_init__(adapted)

    retained = attempt.gate
    if retained is not None:
        _validate_gate(context.approved_gate, retained, adapted, attempt.source_evidence)
    else:
        _require(attempt.source_evidence is None, "Attached evidence requires the retained LIVE gate.")

    if attempt.b2_result is not None:
        _require(retained is not None, "Retained B2 requires the retained LIVE gate.")
        _validate_result(attempt.b2_result, attempt.source_evidence)
        output = attempt.b2_result.receipt_output
        if output is not None:
            _require(output.extractor_version == EXTRACTOR_VERSION, "Unexpected retained B2 extractor.")


def _validate_gate(
    approved: LiveGateApprovalV0 | None,
    retained: RetainedLiveGateV0,
    adapted: AdaptedOcrSource | None,
    evidence: ReceiptSourceEvidence | None,
) -> None:
    _require(
        type(approved) is LiveGateApprovalV0
        and type(retained) is RetainedLiveGateV0
        and retained.policy is approved,
        "A separately approved LIVE gate is required.",
    )
    _protocol_id(approved.policy_id)
    _protocol_id(approved.revision)
    _require(
        type(approved.policy_sha256) is str and _DIGEST.fullmatch(approved.policy_sha256) is not None
        and approved.policy_id != GATE_C_SOURCE_GATE_V0.policy_id
        and approved.policy_sha256 != GATE_C_SOURCE_GATE_V0.canonical_sha256.lower(),
        "Generated-only Gate C or invalid LIVE policy is forbidden.",
    )
    _require(
        adapted is not None and retained.adapted_source is adapted
        and type(evidence) is ReceiptSourceEvidence and evidence.gate_result is retained.result,
        "LIVE gate and evidence must retain the exact OCR and gate objects.",
    )
    _validate_source(adapted, evidence)

    reasons = retained.result.reasons
    ocr_text = {token.original_text for token in adapted.tokens}
    _require(
        type(approved.public_reasons) is tuple
        and all(type(reason) is str for reason in approved.public_reasons)
        and all(reason in approved.public_reasons
                and reason not in _GENERATED_GATE_REASONS
                and reason not in ocr_text for reason in reasons),
        "LIVE gate reasons must be approved public literals.",
    )


def _outcome(attempt: RetainedLocalImageAttemptV0) -> dict[str, object]:
    failure = attempt.failure
    result = attempt.b2_result
    if failure is None:
        _require(result is not None, "A terminal retained B2 result is required.")
        status = "RESULT_AVAILABLE" if result.receipt_output is not None else "SOURCE_EVIDENCE_INSUFFICIENT"
        return {"status": status, "failure": None}

    _require(type(failure) is LocalImageFailureV0, "Invalid terminal failure.")
    stage, code, retryable = failure.value
    if failure is LocalImageFailureV0.PRESENTATION_PROJECTION_FAILURE:
        _require(result is not None and result.receipt_output is not None,
                 "Presentation failure requires the original successful B2 result.")
    else:
        _require(result is None, "This failure stage cannot retain a B2 result.")
    # The frozen V1 validator checks the evidence and gate states for each stage.
    return {
        "status": "PROCESSING_UNAVAILABLE" if stage == "AVAILABILITY" else "PROCESSING_FAILED",
        "failure": {"stage": stage, "code": code, "retryable": retryable},
    }


def _receipt(
    output: ReceiptOutput, tokens: dict[str, str], namespace: str,
) -> dict[str, object]:
    top = (output.store_name, output.purchase_date, output.receipt_total)
    fields = _aliases(
        tuple(field.field_id for field in top)
        + tuple(field.field_id for row in output.items for field in row.fields),
        "fld", namespace,
    )
    rows = _aliases(tuple(row.row_id for row in output.items), "row", namespace)
    return {
        "receiptId": f"rct-v1-{namespace}-1",
        "currencyCode": "MYR",
        "receiptFields": [
            _field_object(field, fields, tokens, f"$.receipt.receiptFields[{index}]")
            for index, field in enumerate(top)
        ],
        "itemRows": [
            {
                "rowId": rows[row.row_id],
                "fields": [
                    _field_object(
                        field, fields, tokens, f"$.receipt.itemRows[{index}].fields[{item_index}]",
                    )
                    for item_index, field in enumerate(row.fields)
                ],
            }
            for index, row in enumerate(output.items)
        ],
    }


def _automatic_output(attempt: RetainedLocalImageAttemptV0) -> tuple[ReceiptOutput | None, str]:
    if attempt.failure is not None:
        return None, "B2"
    baseline = attempt.b2_result.receipt_output
    correction = attempt.correction
    if attempt.proposed is not None:
        _require(correction is None, "Only one correction producer is allowed.")
        return _proposed_output(attempt, baseline)
    if correction is None:
        return baseline, "B2"

    from pipeline.proposed.purchase_date_correction_v0 import (
        PRODUCER_ID, PRODUCER_VERSION,
        PurchaseDateCorrectionOutcomeV0, PurchaseDateCorrectionResultV0,
    )

    _require(type(correction) is PurchaseDateCorrectionResultV0
             and correction.baseline is attempt.b2_result and baseline is not None,
             "Correction must retain the exact B2 result.")
    output = correction.final_output
    if correction.outcome is not PurchaseDateCorrectionOutcomeV0.CORRECT:
        _require(output is baseline, "An unapplied correction must preserve B2.")
        return baseline, "B2"
    recommendation = correction.recommendation
    _require(
        recommendation is not None and recommendation.preferred is not None
        and recommendation.original.value == baseline.purchase_date.value
        and type(output) is ReceiptOutput and output.extractor_version == PRODUCER_VERSION
        and output.receipt_id == baseline.receipt_id
        and output.source_evidence is baseline.source_evidence
        and output.store_name is baseline.store_name
        and output.items is baseline.items
        and output.receipt_total is baseline.receipt_total
        and output.extraction_status is baseline.extraction_status
        and output.purchase_date.field_id == baseline.purchase_date.field_id
        and output.purchase_date.status is baseline.purchase_date.status
        and output.purchase_date.value == recommendation.preferred.value
        and output.purchase_date.confidence is None
        and output.purchase_date.value != baseline.purchase_date.value,
        "Correction must replace only the purchase-date field.",
    )
    return output, PRODUCER_ID


def _proposed_output(attempt, baseline) -> tuple[ReceiptOutput, str]:
    from pipeline.proposed.receipt_context_v1 import ordered_fields
    from pipeline.proposed.receipt_research_v1 import (
        VERSION, ProposedReceiptResearchResult, ResearchMethodState,
    )

    result = attempt.proposed
    _require(type(result) is ProposedReceiptResearchResult and baseline is not None
             and result.correction.baseline is attempt.b2_result,
             "Proposed method must retain the exact B2 result.")
    if result.state is ResearchMethodState.NOT_READY:
        _require(result.output is None and result.receipt_output is None and not result.audits,
                 "Unverified review cannot include a policy output.")
        return replace(baseline, extractor_version=VERSION), PROPOSED_UNVERIFIED_PRODUCER

    output = result.receipt_output
    _require(result.state is ResearchMethodState.POLICY_APPLIED and type(output) is ReceiptOutput
             and result.output is not None and result.output.disposition.gate_result is baseline.source_evidence.gate_result
             and output.source_evidence is baseline.source_evidence and output.receipt_id == baseline.receipt_id
             and output.extractor_version == VERSION,
             "Proposed policy output must bind to the retained OCR and gate.")
    fields = ordered_fields(output)
    prediction = result.output.prediction
    predicted_fields = {
        field.runtime_field_id: field
        for field in (*prediction.receipt_fields, *(f for row in prediction.rows for f in row.fields))
    }
    _require(
        tuple((f.field_id, f.item_row_id, f.field_name) for f in fields)
        == tuple((f.field_id, f.item_row_id, f.field_name) for f in ordered_fields(baseline))
        and tuple((f.field_id, f.value) for f in fields)
        == tuple((d.field_id, d.prediction) for d in result.output.decisions)
        and all(f.confidence is None
                and f.source_token_ids == predicted_fields[f.field_id].source_token_ids
                and f.status is predicted_fields[f.field_id].status
                and f.unresolved_reason == predicted_fields[f.field_id].unresolved_reason for f in fields),
        "Proposed field identities, values or confidence differ from the verified output.",
    )
    return output, PROPOSED_POLICY_PRODUCER


def _build_envelope(
    context: LocalImagePresentationContextV0, attempt: RetainedLocalImageAttemptV0,
) -> dict[str, object]:
    _validate_attempt(context, attempt)
    outcome = _outcome(attempt)
    adapted = attempt.adapted_source
    gate = None if attempt.gate is None else attempt.gate.result
    namespace = context.alias_namespace
    tokens = {} if adapted is None else _aliases(
        tuple(token.token_id for token in adapted.tokens), "tok", namespace,
    )
    output, producer_id = _automatic_output(attempt)
    return {
        "schemaName": "receipt-presentation",
        "schemaVersion": "1",
        "sourceContractVersion": CONTRACT_VERSION,
        "requestId": attempt.request_id,
        "imageId": attempt.image_id,
        "source": {"type": "LOCAL_IMAGE", "provenance": {
            "sourceSystem": LOCAL_IMAGE_SOURCE_SYSTEM,
            "sourceReference": context.source_reference,
            "contentSha256": None,
        }},
        "outcome": outcome,
        "sourceEvidence": None if adapted is None else {
            "sourceProcessingStatus": adapted.processing_status.value,
            "tokenIds": list(tokens.values()),
        },
        "sourceGate": None if gate is None else {
            "gateResultId": f"gat-v1-{namespace}-1",
            "decision": gate.decision.value,
            "reasons": list(gate.reasons),
        },
        "automaticExtraction": None if output is None else {
            "stage": output.output_stage.value,
            "extractionStatus": output.extraction_status.value,
            "producer": {"producerId": producer_id, "producerVersion": output.extractor_version},
        },
        "receipt": None if output is None else _receipt(output, tokens, namespace),
    }


def project_retained_local_image_presentation_v1(
    *, context: LocalImagePresentationContextV0, attempt: RetainedLocalImageAttemptV0,
) -> bytes:
    """Return validated V1 JSON bytes or a refusal with no upstream detail."""

    try:
        envelope = _build_envelope(context, attempt)
        payload = json.dumps(
            envelope, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"),
        ).encode("utf-8")
        decode_and_validate_presentation_v1(
            payload,
            expected_request_id=context.request_id,
            expected_image_id=context.image_id,
            consumer_mode="LIVE",
        )
        return payload
    except LocalImageProjectionError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        pass
    raise LocalImageProjectionError("Retained records cannot be emitted as Receipt Presentation V1.") from None
