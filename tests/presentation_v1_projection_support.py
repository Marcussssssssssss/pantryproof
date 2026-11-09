"""Test-only Contract V0 projection support for receipt-presentation-v1.

This module deliberately lives under ``tests``.  It handcrafts synthetic V1
objects from genuine immutable Contract V0 objects so conformance tests can
check the presentation boundary without invoking OCR, an extractor, a source
gate, proposed-method code, or evaluation code.  It is not a runtime gateway.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from pipeline.contracts import (
    FieldStatus,
    OutputStage,
    ReceiptFieldName,
    ReceiptOutput,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    StructuredField,
)


_ORIGINAL_MONEY = re.compile(
    r"^(?:(?P<prefix>RM|MYR)[ ]*)?"
    r"(?P<amount>(?:0|[1-9][0-9]*)|(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+))"
    r"(?P<fraction>\.[0-9]{2})$",
    re.IGNORECASE,
)

_MONEY_ROLES = {
    ReceiptFieldName.UNIT_PRICE,
    ReceiptFieldName.LINE_TOTAL,
    ReceiptFieldName.RECEIPT_TOTAL,
}

_PROTOCOL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PRIVATE_ID_MARKER = re.compile(
    r"(?:^|[._-])(?:participant|evaluation|ground[-_]?truth|annotation|held[-_]?out)"
    r"(?:$|[._-])",
    re.IGNORECASE | re.ASCII,
)
_URI_OR_WINDOWS_PATH = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|[A-Za-z]:[\\/])")


def project_available_receipt(
    output: ReceiptOutput,
    *,
    request_id: str,
    image_id: str,
    producer_id: str,
) -> dict[str, Any]:
    """Project a genuine synthetic Contract V0 output into a V1 object.

    ``producer_id`` is intentionally mandatory.  ``producerVersion`` always
    comes from ``ReceiptOutput.extractor_version``; this helper neither selects
    nor names a production extractor.  The caller-provided image identity must
    exactly match the immutable evidence identity.
    """

    if not isinstance(output, ReceiptOutput):
        raise TypeError("output must be a Contract V0 ReceiptOutput")
    _require_protocol_id(request_id, "request_id")
    _require_protocol_id(image_id, "image_id")
    _require_protocol_id(producer_id, "producer_id")
    if output.output_stage is not OutputStage.PRE_REVIEW_AUTOMATIC:
        raise ValueError("Only PRE_REVIEW_AUTOMATIC Contract V0 output may be projected")
    evidence = output.source_evidence
    _validate_evidence(evidence, expected_image_id=image_id)
    if evidence.gate_result.decision is not SourceEvidenceDecision.SUFFICIENT:
        raise ValueError("An available result requires the recorded SUFFICIENT gate")
    _validate_output_integrity(output)

    return _base_envelope(
        request_id=request_id,
        image_id=image_id,
        evidence=evidence,
        outcome={"status": "RESULT_AVAILABLE", "failure": None},
        automatic_extraction={
            "stage": output.output_stage.value,
            "extractionStatus": output.extraction_status.value,
            "producer": {
                "producerId": producer_id,
                "producerVersion": output.extractor_version,
            },
        },
        receipt={
            "receiptId": output.receipt_id,
            "currencyCode": "MYR",
            "receiptFields": [
                _project_field(output.store_name),
                _project_field(output.purchase_date),
                _project_field(output.receipt_total),
            ],
            "itemRows": [
                {
                    "rowId": row.row_id,
                    "fields": [_project_field(field) for field in row.fields],
                }
                for row in output.items
            ],
        },
    )


def project_insufficient_source_evidence(
    evidence: ReceiptSourceEvidence,
    *,
    request_id: str,
    image_id: str,
) -> dict[str, Any]:
    """Project genuine synthetic insufficient evidence without a receipt.

    Contract V0 correctly forbids constructing ``ReceiptOutput`` from an
    insufficient gate, so this path accepts evidence directly and emits no
    automatic extraction or receipt content.
    """

    if not isinstance(evidence, ReceiptSourceEvidence):
        raise TypeError("evidence must be Contract V0 ReceiptSourceEvidence")
    _require_protocol_id(request_id, "request_id")
    _require_protocol_id(image_id, "image_id")
    _validate_evidence(evidence, expected_image_id=image_id)
    if evidence.gate_result.decision is not SourceEvidenceDecision.INSUFFICIENT:
        raise ValueError(
            "SOURCE_EVIDENCE_INSUFFICIENT requires the recorded INSUFFICIENT gate"
        )
    if not evidence.gate_result.reasons:
        raise ValueError("An insufficient gate requires recorded reasons")

    return _base_envelope(
        request_id=request_id,
        image_id=image_id,
        evidence=evidence,
        outcome={"status": "SOURCE_EVIDENCE_INSUFFICIENT", "failure": None},
        automatic_extraction=None,
        receipt=None,
    )


def _base_envelope(
    *,
    request_id: str,
    image_id: str,
    evidence: ReceiptSourceEvidence,
    outcome: Mapping[str, Any],
    automatic_extraction: Mapping[str, Any] | None,
    receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    # Never project raw Contract V0 source_system/source_reference/digest.  A
    # deterministic opaque test reference provides correlation without leaking
    # paths, URIs, participant/evaluation identifiers, or image content hashes.
    opaque_source_reference = "source-" + hashlib.sha256(
        image_id.encode("utf-8")
    ).hexdigest()[:24]
    gate = evidence.gate_result
    return {
        "schemaName": "receipt-presentation",
        "schemaVersion": "1",
        "sourceContractVersion": "0",
        "requestId": request_id,
        "imageId": image_id,
        "source": {
            "type": "SYNTHETIC_FIXTURE",
            "provenance": {
                "sourceSystem": "M3E_SYNTHETIC_V0",
                "sourceReference": opaque_source_reference,
                "contentSha256": None,
            },
        },
        "outcome": dict(outcome),
        "sourceEvidence": {
            "sourceProcessingStatus": evidence.processing_status.value,
            "tokenIds": [token.token_id for token in evidence.tokens],
        },
        "sourceGate": {
            "gateResultId": gate.gate_result_id,
            "decision": gate.decision.value,
            "reasons": list(gate.reasons),
        },
        "automaticExtraction": (
            None if automatic_extraction is None else dict(automatic_extraction)
        ),
        "receipt": None if receipt is None else dict(receipt),
    }


def _project_field(field: StructuredField) -> dict[str, Any]:
    if field.status is FieldStatus.EXTRACTED:
        assert field.value is not None  # Guaranteed by Contract V0.
        original_value = field.value
        presentation_value = _canonical_presentation_value(field)
    else:
        original_value = None
        presentation_value = None

    return {
        "fieldId": field.field_id,
        "role": field.field_name.value,
        "status": field.status.value,
        "originalAutomaticValue": original_value,
        "presentationValue": presentation_value,
        "absenceReason": field.unresolved_reason,
        "sourceTokenIds": list(field.source_token_ids),
        "nativeConfidence": field.confidence,
    }


def _canonical_presentation_value(field: StructuredField) -> str:
    """Apply only the approved deterministic lexical V1 normalization."""

    assert field.value is not None
    if field.field_name not in _MONEY_ROLES:
        # Store/description, ISO date, and quantity are identity mappings.  The
        # production semantic validator determines whether their grammar is V1.
        return field.value

    match = _ORIGINAL_MONEY.fullmatch(field.value)
    if match is None:
        raise ValueError(
            f"Field {field.field_id!r} has money that cannot be canonically projected"
        )
    return match.group("amount").replace(",", "") + match.group("fraction")


def _validate_evidence(
    evidence: ReceiptSourceEvidence, *, expected_image_id: str
) -> None:
    _require_protocol_id(evidence.receipt_id, "evidence.receipt_id")
    _require_protocol_id(evidence.image_id, "evidence.image_id")
    if evidence.image_id != expected_image_id:
        raise ValueError("Contract V0 evidence image_id does not match caller identity")
    token_ids = [token.token_id for token in evidence.tokens]
    for token_id in token_ids:
        _require_protocol_id(token_id, "evidence token_id")
    if len(token_ids) != len(set(token_ids)):
        raise ValueError("Contract V0 evidence contains duplicate token IDs")
    if any(token.receipt_id != evidence.receipt_id for token in evidence.tokens):
        raise ValueError("Contract V0 evidence token receipt identity mismatch")
    if evidence.gate_result.receipt_id != evidence.receipt_id:
        raise ValueError("Contract V0 gate/evidence receipt identity mismatch")
    _require_protocol_id(
        evidence.gate_result.gate_result_id, "evidence.gate_result.gate_result_id"
    )
    for reason in evidence.gate_result.reasons:
        _require_privacy_safe_reason(reason, "source-gate reason")


def _validate_output_integrity(output: ReceiptOutput) -> None:
    evidence = output.source_evidence
    _require_protocol_id(output.receipt_id, "output.receipt_id")
    if output.receipt_id != evidence.receipt_id:
        raise ValueError("Contract V0 output/evidence receipt identity mismatch")
    token_ids = evidence.token_ids
    fields = [output.store_name, output.purchase_date, output.receipt_total]
    for row in output.items:
        _require_protocol_id(row.row_id, "output item row_id")
        fields.extend(row.fields)
    for field in fields:
        _require_protocol_id(field.field_id, "output field_id")
        if field.unresolved_reason is not None:
            _require_privacy_safe_reason(field.unresolved_reason, "field absence reason")
    if any(field.receipt_id != output.receipt_id for field in fields):
        raise ValueError("Contract V0 field/output receipt identity mismatch")
    unknown = {
        token_id
        for field in fields
        for token_id in field.source_token_ids
        if token_id not in token_ids
    }
    if unknown:
        raise ValueError(f"Contract V0 fields reference unknown tokens: {sorted(unknown)}")


def _require_nonblank(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip("\t\n\r "):
        raise ValueError(f"{name} must be a nonblank string")


def _require_protocol_id(value: str, name: str) -> None:
    _require_nonblank(value, name)
    if _PROTOCOL_ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be a privacy-safe protocol identifier")


def _require_privacy_safe_reason(value: str, name: str) -> None:
    _require_nonblank(value, name)
    if (
        _URI_OR_WINDOWS_PATH.search(value) is not None
        or value.startswith("/")
        or _PRIVATE_ID_MARKER.search(value) is not None
    ):
        raise ValueError(f"{name} contains prohibited path, URI, or private identity")

