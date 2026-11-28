"""Synthetic evidence-first B2 execution and strict Presentation V1 emission.

The trusted caller evaluates its synthetic gate and attaches evidence once before
calling this module. The extracting entry point calls B2 once; the retained-result
entry point calls no upstream stages. Neither calls L01 or reattaches evidence.
Aliases are invocation-local, not authenticated identities
or a request/replay registry. No operational processing or failure envelope is
provided. Public failures deliberately omit upstream messages and traceback
chains, which may contain private source identifiers.
"""

from __future__ import annotations

import json
from math import isfinite
import re

from pipeline.contracts import (
    CONTRACT_VERSION,
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
from pipeline.layout_b2 import B2ExtractionResult, extract_b2
from pipeline.ocr_adapter import AdaptedOcrSource
from pipeline.presentation_v1.conformance import (
    ConformanceViolation,
    decode_and_validate_presentation_v1,
)

__all__ = (
    "extract_b2_fixture_presentation_v1",
    "project_retained_b2_fixture_presentation_v1",
)

_NAMESPACE = re.compile(r"[0-9a-f]{32}")
_PROTOCOL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_PRIVATE_ID = re.compile(
    r"(?:\A|[._-])(?:participant|evaluation|ground[-_]?truth|annotation|held[-_]?out)"
    r"(?:\Z|[._-])", re.IGNORECASE | re.ASCII,
)
# Only the approved lexical money transformation is performed here. All final
# field semantics remain the existing V1 validator's job. L02's narrower
# synthetic reason admission runs only after that validation succeeds.
_ORIGINAL_MONEY = re.compile(
    r"(?:(?i:RM|MYR)[ ]*)?"
    r"(?P<integer>(?:0|[1-9][0-9]*)|(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+))"
    r"\.(?P<fraction>[0-9]{2})", re.ASCII,
)
_RECEIPT_ROLES = (
    ReceiptFieldName.STORE_NAME, ReceiptFieldName.PURCHASE_DATE,
    ReceiptFieldName.RECEIPT_TOTAL,
)
_ITEM_ROLES = (
    ReceiptFieldName.ITEM_DESCRIPTION, ReceiptFieldName.QUANTITY,
    ReceiptFieldName.UNIT_PRICE, ReceiptFieldName.LINE_TOTAL,
)
_MONEY_ROLES = frozenset((
    ReceiptFieldName.UNIT_PRICE, ReceiptFieldName.LINE_TOTAL,
    ReceiptFieldName.RECEIPT_TOTAL,
))
_SYNTHETIC_GATE_REASONS = frozenset((
    "Synthetic source structure was unavailable.",
    "There is 1 unreadable row.",
    "The x marker was unavailable.",
    "Extraction could not locate 1 safe heading.",
))
_DIAGNOSTIC_CODES = frozenset((
    "REJECT_CONTRADICTORY_FIELD_STATE", "REJECT_CURRENCY_METADATA", "REJECT_CURRENCY_MISMATCH",
    "REJECT_DUPLICATE_FIELD_ID", "REJECT_DUPLICATE_JSON_KEY", "REJECT_DUPLICATE_ROW_ID",
    "REJECT_DUPLICATE_TOKEN_ID", "REJECT_DUPLICATE_TOKEN_REFERENCE", "REJECT_EVIDENCE_STAGE_MISMATCH",
    "REJECT_GATE_OUTCOME_MISMATCH", "REJECT_GATE_STATE", "REJECT_IMAGE_ID_MISMATCH",
    "REJECT_INVALID_CONFIDENCE", "REJECT_INVALID_DATE", "REJECT_INVALID_DIGEST", "REJECT_INVALID_ID",
    "REJECT_INVALID_JSON", "REJECT_INVALID_MONEY", "REJECT_INVALID_QUANTITY", "REJECT_MISSING_MEMBER",
    "REJECT_OUTCOME_STAGE_MISMATCH", "REJECT_OUTCOME_STATE_MISMATCH", "REJECT_PRODUCER_METADATA",
    "REJECT_REQUEST_ID_MISMATCH", "REJECT_ROLE_ORDER", "REJECT_ROLE_SET", "REJECT_SOURCE_MODE_MISMATCH",
    "REJECT_TOKEN_INTEGRITY", "REJECT_UNKNOWN_ENUM", "REJECT_UNKNOWN_MEMBER", "REJECT_UNKNOWN_ROLE",
    "REJECT_UNKNOWN_TOKEN_REFERENCE", "REJECT_UNSAFE_PROVENANCE",
    "REJECT_UNSUPPORTED_CONTRACT_VERSION", "REJECT_UNSUPPORTED_SCHEMA_VERSION", "REJECT_VALUE_RELATIONSHIP",
))
_CONTEXT_PATHS = frozenset((
    "$context.mode", "$context.expectedRequestId", "$context.expectedImageId",
))
# This closed schema describes paths only; it does not replace V1 validation.
# Dicts are object members, one-element tuples are arrays, None is a scalar.
_FIELD_PATH_SCHEMA = dict.fromkeys((
    "fieldId", "role", "status", "originalAutomaticValue", "presentationValue",
    "absenceReason", "nativeConfidence",
))
_FIELD_PATH_SCHEMA["sourceTokenIds"] = (None,)
_PATH_SCHEMA = {
    **dict.fromkeys(("schemaName", "schemaVersion", "sourceContractVersion", "requestId", "imageId")),
    "source": {"type": None, "provenance": dict.fromkeys((
        "sourceSystem", "sourceReference", "contentSha256",
    ))},
    "outcome": {"status": None, "failure": dict.fromkeys(("stage", "code", "retryable"))},
    "sourceEvidence": {"sourceProcessingStatus": None, "tokenIds": (None,)},
    "sourceGate": {"gateResultId": None, "decision": None, "reasons": (None,)},
    "automaticExtraction": {"stage": None, "extractionStatus": None, "producer": dict.fromkeys((
        "producerId", "producerVersion",
    ))},
    "receipt": {"receiptId": None, "currencyCode": None, "receiptFields": (_FIELD_PATH_SCHEMA,),
                "itemRows": ({"rowId": None, "fields": (_FIELD_PATH_SCHEMA,)},)},
}
_PATH_STEP = re.compile(r"\.([A-Za-z][A-Za-z0-9]*)|\[([0-9]+)\]", re.ASCII)


def _verified_diagnostic_path(path: str, structure: object) -> bool:
    if path == "$" or path in _CONTEXT_PATHS:
        return True
    if not path.startswith("$."):
        return False
    schema = _PATH_SCHEMA
    position = 1
    while position < len(path):
        step = _PATH_STEP.match(path, position)
        if step is None:
            return False
        member, digits = step.groups()
        if member is not None:
            if type(schema) is not dict or member not in schema:
                return False
            schema = schema[member]
            structure = structure.get(member) if type(structure) is dict else None
        else:
            if type(schema) is not tuple or type(structure) not in (list, tuple) or not structure:
                return False
            if len(digits) > 1 and digits[0] == "0":
                return False
            # Compare canonical decimal strings before int conversion, including
            # hostile enormous indices. Bounds come from this emission, not text.
            maximum = str(len(structure) - 1)
            if len(digits) > len(maximum) or (len(digits) == len(maximum) and digits > maximum):
                return False
            structure = structure[int(digits)]
            schema = schema[0]
        position = step.end()
    return True


def _diagnostic_bounds(evidence: ReceiptSourceEvidence, result: B2ExtractionResult) -> dict:
    """Establish array bounds from validated records before money projection.

    Once construction succeeds the actual envelope replaces this shape. No
    payload-supplied keys ever define the permitted schema member vocabulary.
    """
    output = result.receipt_output
    receipt = None
    if output is not None:
        receipt = {
            "receiptFields": [{"sourceTokenIds": field.source_token_ids} for field in (
                output.store_name, output.purchase_date, output.receipt_total,
            )],
            "itemRows": [{"fields": [{"sourceTokenIds": field.source_token_ids}
                                      for field in row.fields]} for row in output.items],
        }
    return {
        "sourceEvidence": {"tokenIds": evidence.tokens},
        "sourceGate": {"reasons": evidence.gate_result.reasons},
        "receipt": receipt,
    }


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid synthetic projection association.")


def _text(value: object) -> None:
    _require(type(value) is str and bool(value.strip()))


def _protocol_id(value: object) -> None:
    _require(type(value) is str and _PROTOCOL_ID.fullmatch(value) is not None)
    _require(_PRIVATE_ID.search(value) is None)


def _native_number(value: object) -> None:
    # Contract V0 native numbers are int/float, not bool, Decimal, or arbitrary
    # objects convertible to float. No conversion or calibration is introduced.
    _require(type(value) in (int, float) and isfinite(value))


def _validate_source(adapted: AdaptedOcrSource, evidence: ReceiptSourceEvidence) -> None:
    _require(isinstance(adapted, AdaptedOcrSource))
    _require(isinstance(evidence, ReceiptSourceEvidence))
    _text(adapted.receipt_id)
    _text(adapted.image_id)
    _require(isinstance(adapted.processing_status, SourceProcessingStatus))
    _require(type(adapted.tokens) is tuple)
    _require(isinstance(adapted.provenance, SourceProvenance))
    _text(adapted.provenance.source_system)
    _text(adapted.provenance.source_reference)
    if adapted.provenance.content_sha256 is not None:
        _text(adapted.provenance.content_sha256)
    SourceProvenance.__post_init__(adapted.provenance)
    for token in adapted.tokens:
        _require(isinstance(token, OcrSourceToken))
        _text(token.receipt_id)
        _text(token.token_id)
        _require(type(token.original_text) is str)
        _require(type(token.polygon) is tuple)
        for point in token.polygon:
            _require(isinstance(point, Point))
            _native_number(point.x)
            _native_number(point.y)
        if token.raw_confidence is not None:
            _native_number(token.raw_confidence)
        OcrSourceToken.__post_init__(token)
    AdaptedOcrSource.__post_init__(adapted)
    _require(evidence.receipt_id == adapted.receipt_id)
    _require(evidence.image_id == adapted.image_id)
    _require(evidence.processing_status is adapted.processing_status)
    _require(evidence.tokens is adapted.tokens)
    _require(evidence.provenance is adapted.provenance)
    gate = evidence.gate_result
    _require(isinstance(gate, SourceEvidenceGateResult))
    _text(gate.gate_result_id)
    _require(gate.receipt_id == adapted.receipt_id)
    _require(isinstance(gate.decision, SourceEvidenceDecision))
    _require(type(gate.reasons) is tuple)
    for reason in gate.reasons:
        # Gate V0 does not impose StructuredField's Unicode-strip rule. Keep
        # V1's exact nonblank/privacy semantics and diagnostic precedence.
        _require(type(reason) is str)
    SourceEvidenceGateResult.__post_init__(gate)
    ReceiptSourceEvidence.__post_init__(evidence)


def _validate_field(field: StructuredField, role: ReceiptFieldName) -> None:
    _require(isinstance(field, StructuredField))
    _text(field.field_id)
    _text(field.receipt_id)
    _require(field.field_name is role)
    _require(isinstance(field.status, FieldStatus))
    _require(type(field.source_token_ids) is tuple)
    for token_id in field.source_token_ids:
        _text(token_id)
    if field.value is not None:
        _require(type(field.value) is str)
    if field.unresolved_reason is not None:
        _text(field.unresolved_reason)
    if field.confidence is not None:
        _native_number(field.confidence)
    StructuredField.__post_init__(field)


def _validate_result(result: B2ExtractionResult, evidence: ReceiptSourceEvidence) -> None:
    _require(isinstance(result, B2ExtractionResult))
    B2ExtractionResult.__post_init__(result)
    if result.receipt_output is None:
        fallback = result.pre_resolution_disposition
        _require(isinstance(fallback, PreResolutionDisposition))
        _require(fallback.state is PolicyState.FALLBACK_NO_UPDATE)
        _require(fallback.gate_result is evidence.gate_result)
        _require(evidence.gate_result.decision is SourceEvidenceDecision.INSUFFICIENT)
        PreResolutionDisposition.__post_init__(fallback)
        return
    output = result.receipt_output
    _require(isinstance(output, ReceiptOutput))
    _require(output.source_evidence is evidence)
    _require(output.receipt_id == evidence.receipt_id)
    _require(evidence.gate_result.decision is SourceEvidenceDecision.SUFFICIENT)
    _require(output.output_stage is OutputStage.PRE_REVIEW_AUTOMATIC)
    _require(output.contract_version == CONTRACT_VERSION)
    _require(isinstance(output.extraction_status, ReceiptExtractionStatus))
    _text(output.extractor_version)
    _require(type(output.items) is tuple)
    for field, role in zip(
        (output.store_name, output.purchase_date, output.receipt_total), _RECEIPT_ROLES,
    ):
        _validate_field(field, role)
    for row in output.items:
        _require(isinstance(row, ReceiptItemRow))
        _text(row.row_id)
        _text(row.receipt_id)
        for field, role in zip(row.fields, _ITEM_ROLES):
            _validate_field(field, role)
        ReceiptItemRow.__post_init__(row)
    # Includes receipt-wide field/row uniqueness, ownership and reference checks.
    ReceiptOutput.__post_init__(output)


def _aliases(identities: tuple[str, ...], kind: str, namespace: str) -> dict[str, str]:
    _require(len(identities) == len(set(identities)))
    aliases = {
        original: f"{kind}-v1-{namespace}-{ordinal}"
        for ordinal, original in enumerate(identities, 1)
    }
    _require(len(aliases) == len(set(aliases.values())) == len(identities))
    return aliases


def _field_object(
    field: StructuredField, fields: dict[str, str], tokens: dict[str, str], path: str,
) -> dict[str, object]:
    presentation = field.value
    if field.status is FieldStatus.EXTRACTED and field.field_name in _MONEY_ROLES:
        if field.value.startswith("$"):
            raise ConformanceViolation(
                "REJECT_CURRENCY_MISMATCH", f"{path}.originalAutomaticValue",
                "Original money is not established as MYR.",
            )
        match = _ORIGINAL_MONEY.fullmatch(field.value)
        if match is None:
            raise ConformanceViolation(
                "REJECT_VALUE_RELATIONSHIP", f"{path}.originalAutomaticValue",
                "Original money is outside the approved lexical grammar.",
            )
        presentation = match["integer"].replace(",", "") + "." + match["fraction"]
    return {
        "fieldId": fields[field.field_id], "role": field.field_name.value,
        "status": field.status.value, "originalAutomaticValue": field.value,
        "presentationValue": presentation, "absenceReason": field.unresolved_reason,
        "sourceTokenIds": [tokens[token_id] for token_id in field.source_token_ids],
        "nativeConfidence": field.confidence,
    }


def _envelope(
    evidence: ReceiptSourceEvidence, result: B2ExtractionResult,
    request_id: str, image_id: str, namespace: str, producer_id: str,
) -> dict[str, object]:
    tokens = _aliases(tuple(token.token_id for token in evidence.tokens), "tok", namespace)
    output = result.receipt_output
    receipt = extraction = None
    if output is not None:
        top = (output.store_name, output.purchase_date, output.receipt_total)
        all_fields = top + tuple(field for row in output.items for field in row.fields)
        fields = _aliases(tuple(field.field_id for field in all_fields), "fld", namespace)
        rows = _aliases(tuple(row.row_id for row in output.items), "row", namespace)
        receipt = {
            "receiptId": f"rct-v1-{namespace}-1", "currencyCode": "MYR",
            "receiptFields": [
                _field_object(field, fields, tokens, f"$.receipt.receiptFields[{i}]")
                for i, field in enumerate(top)
            ],
            "itemRows": [
                {"rowId": rows[row.row_id], "fields": [
                    _field_object(
                        field, fields, tokens, f"$.receipt.itemRows[{i}].fields[{j}]",
                    ) for j, field in enumerate(row.fields)
                ]} for i, row in enumerate(output.items)
            ],
        }
        extraction = {
            "stage": output.output_stage.value,
            "extractionStatus": output.extraction_status.value,
            "producer": {"producerId": producer_id, "producerVersion": output.extractor_version},
        }
    return {
        "schemaName": "receipt-presentation", "schemaVersion": "1",
        "sourceContractVersion": CONTRACT_VERSION, "requestId": request_id, "imageId": image_id,
        "source": {"type": "SYNTHETIC_FIXTURE", "provenance": {
            "sourceSystem": "I2B_SYNTHETIC_B2_V0",
            "sourceReference": f"src-v1-{namespace}-1", "contentSha256": None,
        }},
        "outcome": {
            "status": "RESULT_AVAILABLE" if output is not None else "SOURCE_EVIDENCE_INSUFFICIENT",
            "failure": None,
        },
        "sourceEvidence": {
            "sourceProcessingStatus": evidence.processing_status.value,
            "tokenIds": list(tokens.values()),
        },
        "sourceGate": {
            "gateResultId": f"gat-v1-{namespace}-1",
            "decision": evidence.gate_result.decision.value,
            "reasons": list(evidence.gate_result.reasons),
        },
        "automaticExtraction": extraction, "receipt": receipt,
    }


def _reject_literal_ocr_gate_reasons(evidence: ReceiptSourceEvidence) -> None:
    """Admit only reviewed literal synthetic reasons, with an OCR equality veto.

    Compare original strings exactly: no substring matching, length threshold,
    trimming, case folding or rewriting. A short token such as '1' or 'x' must
    not make unrelated prose unsafe. Existing V1 validation runs first so its
    nonblank, privacy and structural rejection precedence remains unchanged.
    """
    transcriptions = frozenset(token.original_text for token in evidence.tokens)
    for index, reason in enumerate(evidence.gate_result.reasons):
        if reason not in _SYNTHETIC_GATE_REASONS or reason in transcriptions:
            raise ConformanceViolation(
                "REJECT_UNSAFE_PROVENANCE", f"$.sourceGate.reasons[{index}]",
                "Synthetic projection rejected.",
            )


def extract_b2_fixture_presentation_v1(
    *,
    adapted_source: AdaptedOcrSource,
    source_evidence: ReceiptSourceEvidence,
    request_id: str,
    image_id: str,
    alias_namespace: str,
    producer_id: str,
    consumer_mode: str,
) -> bytes:
    """Execute B2 once from retained synthetic evidence and emit validated V1.

    All identities are caller supplied. Image equality is a limited synthetic
    prebinding, not a general wire-ID remapper. Failed calls return no envelope.
    Failure propagation uses safe exception text rather than publishing upstream
    messages, chained tracebacks or private record representations.
    """
    return _produce_fixture_presentation_v1(
        adapted_source=adapted_source, source_evidence=source_evidence,
        b2_result=None, run_extraction=True, request_id=request_id, image_id=image_id,
        alias_namespace=alias_namespace, producer_id=producer_id, consumer_mode=consumer_mode,
    )


def project_retained_b2_fixture_presentation_v1(
    *,
    adapted_source: AdaptedOcrSource,
    source_evidence: ReceiptSourceEvidence,
    b2_result: B2ExtractionResult,
    request_id: str,
    image_id: str,
    alias_namespace: str,
    producer_id: str,
    consumer_mode: str,
) -> bytes:
    """Project an original retained synthetic B2 result without executing B2.

    The caller owns and retains all original stage records. This checks their
    associations, not historical execution authenticity. Invalid or missing
    results never cause extraction, evidence reconstruction or a retry.
    """
    return _produce_fixture_presentation_v1(
        adapted_source=adapted_source, source_evidence=source_evidence,
        b2_result=b2_result, run_extraction=False, request_id=request_id, image_id=image_id,
        alias_namespace=alias_namespace, producer_id=producer_id, consumer_mode=consumer_mode,
    )


def _produce_fixture_presentation_v1(
    *,
    adapted_source: AdaptedOcrSource,
    source_evidence: ReceiptSourceEvidence,
    b2_result: B2ExtractionResult | None,
    run_extraction: bool,
    request_id: str,
    image_id: str,
    alias_namespace: str,
    producer_id: str,
    consumer_mode: str,
) -> bytes:
    """Share ordering, mapping and sanitization across both public boundaries.

    Only the extracting entry point selects extraction. Keeping the selection
    inside the existing handler preserves pre-B2 rejection and B2 exception
    classification; retained results proceed directly to result validation.
    """
    stage = "input"
    diagnostic_structure = None
    admitted_diagnostic = None
    try:
        if consumer_mode != "FIXTURE":
            raise ConformanceViolation(
                "REJECT_SOURCE_MODE_MISMATCH", "$context.mode",
                "Synthetic projection requires FIXTURE mode.",
            )
        for identity in (request_id, image_id, producer_id):
            _protocol_id(identity)
        _require(type(alias_namespace) is str and _NAMESPACE.fullmatch(alias_namespace) is not None)
        _validate_source(adapted_source, source_evidence)
        _require(image_id == adapted_source.image_id == source_evidence.image_id)
        if run_extraction:
            stage = "b2"
            result = extract_b2(source_evidence)
        else:
            result = b2_result
        stage = "projection"
        _validate_result(result, source_evidence)
        diagnostic_structure = _diagnostic_bounds(source_evidence, result)
        envelope = _envelope(source_evidence, result, request_id, image_id, alias_namespace, producer_id)
        diagnostic_structure = envelope
        raw = json.dumps(
            envelope, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"),
        ).encode("utf-8")
        decode_and_validate_presentation_v1(
            raw, expected_request_id=request_id, expected_image_id=image_id, consumer_mode="FIXTURE",
        )
        _reject_literal_ocr_gate_reasons(source_evidence)
        return raw
    except Exception as error:
        if stage == "b2":
            failure_kind = "b2"
        elif isinstance(error, ConformanceViolation):
            failure_kind = "projection"
            if type(error) is ConformanceViolation:
                code = getattr(error, "code", None)
                path = getattr(error, "path", None)
                if (type(code) is str and type(path) is str and code in _DIAGNOSTIC_CODES
                        and _verified_diagnostic_path(path, diagnostic_structure)):
                    admitted_diagnostic = (code, path)
        else:
            failure_kind = "input"
    # Construct and raise outside the handler; never retain the original error
    # as public cause/context, notes, args or unverified diagnostic metadata.
    if failure_kind == "b2":
        raise RuntimeError("Synthetic B2 execution failed.") from None
    if failure_kind == "projection":
        if admitted_diagnostic is not None:
            code, path = admitted_diagnostic
            raise ConformanceViolation(code, path, "Synthetic projection rejected.") from None
        raise RuntimeError("Synthetic projection failed.") from None
    raise ValueError("Invalid synthetic B2-to-V1 input or result.") from None
