"""Synthetic-only evidence-first B2/V1 tests; no operational gate policy."""

from __future__ import annotations

import ast
from dataclasses import asdict, replace
import hashlib
import inspect
import json
from pathlib import Path
import traceback
from unittest.mock import Mock, patch

import pytest

from pipeline import backend_receipt_execution_v0 as l01
from pipeline import ocr_adapter
from pipeline.contracts import (
    FieldStatus,
    OutputStage,
    PolicyState,
    ReceiptExtractionStatus,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
)
from pipeline.layout_b2 import EXTRACTOR_VERSION, extract_b2 as real_extract_b2
from pipeline.ocr_adapter import adapt_paddleocr_result, attach_gate_result
from pipeline.presentation_v1 import b2_synthetic_projection_v0 as projection
from pipeline.presentation_v1.conformance import (
    ConformanceViolation,
    decode_and_validate_presentation_v1,
)

NAMESPACE = "0123456789abcdef0123456789abcdef"
REQUEST = "request-synthetic-b2-v1"
IMAGE = "image-synthetic-b2-v1"
PRODUCER = "I2B_SYNTHETIC_B2_PRODUCER"
ROOT = Path(__file__).resolve().parents[1] / "tests/fixtures/receipt_presentation_v1/v1"


def prepare(
    *, decision=SourceEvidenceDecision.SUFFICIENT,
    status=SourceProcessingStatus.OCR_COMPLETED, date="2026-10-13",
    quantity="2", unit="5.50", receipt_total="23.90", empty=False,
    partial=False, no_store=False, reverse_rows=False, reasons=None,
):
    """Evaluate one explicit gate double and retain one real attachment."""
    header = [] if no_store else [("PANTRYPROOF TEST MART", 20, 0, 180)]
    header += [("DATE:", 10, 20, 45), (date, 70, 20, 100)]
    first = [("MILK", 10, 45, 45), (quantity, 110, 45, 10),
             ("x", 130, 45, 8), (unit, 155, 45, 38), ("11.00", 220, 45, 45)]
    second = [("RICE", 10, 65, 45), ("1", 110, 65, 10),
              ("x", 130, 65, 8), ("12.90", 155, 65, 38), ("12.90", 220, 65, 45)]
    if partial:
        body = [("MILK", 10, 45, 140), ("11.00", 230, 45, 45)]
    else:
        body = second + first if reverse_rows else first + second
    regions = [] if empty else header + body + [
        ("TOTAL", 130, 95, 55), (receipt_total, 220, 95, 70),
    ]
    source = adapt_paddleocr_result(
        {"rec_texts": [text for text, *_ in regions],
         "rec_boxes": [[x, y, x + width, y + 10] for _, x, y, width in regions],
         "rec_scores": [(None, -0.0, 0.75)[i % 3] for i in range(len(regions))]},
        receipt_id="private:receipt:synthetic-alpha", image_id=IMAGE,
        source_system="private-original-source-system",
        source_reference="file:///tmp/participant-001.jpg", processing_status=status,
    )
    gate = SourceEvidenceGateResult(
        gate_result_id="private:gate:synthetic-alpha", receipt_id=source.receipt_id,
        decision=decision,
        reasons=reasons if reasons is not None else (
            ("Synthetic source structure was unavailable.",)
            if decision is SourceEvidenceDecision.INSUFFICIENT else ()
        ),
    )
    evaluator = Mock(return_value=gate)
    with patch.object(ocr_adapter, "attach_gate_result", wraps=attach_gate_result) as attach:
        evidence = ocr_adapter.attach_gate_result(source, evaluator(source))
        attach.assert_called_once_with(source, gate)
    evaluator.assert_called_once_with(source)
    assert evidence.gate_result is gate
    assert evidence.tokens is source.tokens
    assert evidence.provenance is source.provenance
    return source, evidence, evaluator


def emit(source, evidence, **changes):
    arguments = dict(
        adapted_source=source, source_evidence=evidence, request_id=REQUEST,
        image_id=IMAGE, alias_namespace=NAMESPACE, producer_id=PRODUCER,
        consumer_mode="FIXTURE",
    )
    arguments.update(changes)
    return projection.extract_b2_fixture_presentation_v1(**arguments)


def validated(raw, request=REQUEST, image=IMAGE, mode="FIXTURE"):
    return decode_and_validate_presentation_v1(
        raw, expected_request_id=request, expected_image_id=image, consumer_mode=mode,
    )


def capture_real_results():
    captured = []

    def execute(evidence):
        result = real_extract_b2(evidence)
        captured.append(result)
        return result

    return captured, execute


def assert_safe_failure(error):
    text = "".join(traceback.format_exception(error))
    for secret in ("participant-001", "private:receipt", "private:gate", "SECRET", "file:///"):
        assert secret not in str(error)
        assert secret not in text
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize("status", list(SourceProcessingStatus))
@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
def test_genuine_b2_outcomes_preserve_source_and_execute_once(status, decision):
    source, evidence, evaluator = prepare(status=status, decision=decision)
    before = repr((asdict(source), asdict(evidence)))
    identities = (id(source.tokens), id(evidence.tokens), id(source.provenance),
                  id(evidence.gate_result), tuple(id(token) for token in source.tokens))
    captured, execute = capture_real_results()
    with patch.object(projection, "extract_b2", side_effect=execute) as b2, \
         patch.object(ocr_adapter, "attach_gate_result", side_effect=AssertionError("reattachment")) as attach, \
         patch.object(l01, "extract_adapted_receipt_v0", side_effect=AssertionError("L01 execution")) as old:
        raw = emit(source, evidence)
    b2.assert_called_once_with(evidence)
    assert b2.call_args.args[0] is evidence
    assert attach.call_count == old.call_count == 0
    evaluator.assert_called_once_with(source)
    result = captured[0]
    wire = json.loads(raw)
    dto = validated(raw)
    assert wire["sourceEvidence"]["sourceProcessingStatus"] == status.value
    assert wire["sourceGate"]["decision"] == decision.value
    assert dto.source_gate.reasons == evidence.gate_result.reasons
    if decision is SourceEvidenceDecision.SUFFICIENT:
        assert result.receipt_output.source_evidence is evidence
        assert result.pre_resolution_disposition is None
        assert wire["outcome"] == {"failure": None, "status": "RESULT_AVAILABLE"}
        assert wire["automaticExtraction"]["extractionStatus"] == result.receipt_output.extraction_status.value
        assert wire["automaticExtraction"]["producer"] == {
            "producerId": PRODUCER, "producerVersion": EXTRACTOR_VERSION,
        }
        assert wire["receipt"]["receiptFields"][0]["originalAutomaticValue"] == "PANTRYPROOF TEST MART"
        assert [row["fields"][0]["presentationValue"] for row in wire["receipt"]["itemRows"]] == ["MILK", "RICE"]
    else:
        assert result.receipt_output is None
        assert result.pre_resolution_disposition.state is PolicyState.FALLBACK_NO_UPDATE
        assert result.pre_resolution_disposition.gate_result is evidence.gate_result
        assert wire["outcome"] == {"failure": None, "status": "SOURCE_EVIDENCE_INSUFFICIENT"}
        assert wire["automaticExtraction"] is wire["receipt"] is None
    assert before == repr((asdict(source), asdict(evidence)))
    assert identities == (id(source.tokens), id(evidence.tokens), id(source.provenance),
                          id(evidence.gate_result), tuple(id(token) for token in source.tokens))


def test_structural_failed_is_actual_available_b2_output():
    source, evidence, _ = prepare(empty=True, status=SourceProcessingStatus.OCR_PARTIAL)
    captured, execute = capture_real_results()
    with patch.object(projection, "extract_b2", side_effect=execute) as b2:
        wire = json.loads(emit(source, evidence))
    b2.assert_called_once_with(evidence)
    assert captured[0].receipt_output.extraction_status is ReceiptExtractionStatus.FAILED
    assert wire["outcome"]["status"] == "RESULT_AVAILABLE"
    assert wire["automaticExtraction"]["extractionStatus"] == "FAILED"
    assert wire["receipt"]["itemRows"] == []
    assert all(field["status"] == "MISSING" for field in wire["receipt"]["receiptFields"])


def test_aliases_order_references_and_all_original_values_match_actual_b2():
    source, evidence, _ = prepare(reverse_rows=True)
    captured, execute = capture_real_results()
    with patch.object(projection, "extract_b2", side_effect=execute):
        raw = emit(source, evidence)
    wire = json.loads(raw)
    output = captured[0].receipt_output
    registry = {token.token_id: f"tok-v1-{NAMESPACE}-{i}" for i, token in enumerate(source.tokens, 1)}
    assert wire["sourceEvidence"]["tokenIds"] == list(registry.values())
    assert wire["sourceGate"]["gateResultId"] == f"gat-v1-{NAMESPACE}-1"
    assert wire["receipt"]["receiptId"] == f"rct-v1-{NAMESPACE}-1"
    assert [row["rowId"] for row in wire["receipt"]["itemRows"]] == [
        f"row-v1-{NAMESPACE}-1", f"row-v1-{NAMESPACE}-2",
    ]
    fields = list((output.store_name, output.purchase_date, output.receipt_total))
    fields.extend(field for row in output.items for field in row.fields)
    projected = list(wire["receipt"]["receiptFields"])
    projected.extend(field for row in wire["receipt"]["itemRows"] for field in row["fields"])
    assert [field["fieldId"] for field in projected] == [f"fld-v1-{NAMESPACE}-{i}" for i in range(1, 12)]
    assert len({field["fieldId"] for field in projected}) == len(projected)
    for original, actual in zip(fields, projected, strict=True):
        assert actual["role"] == original.field_name.value
        assert actual["status"] == original.status.value
        assert actual["originalAutomaticValue"] == original.value
        assert actual["absenceReason"] == original.unresolved_reason
        assert actual["sourceTokenIds"] == [registry[token_id] for token_id in original.source_token_ids]
        assert actual["nativeConfidence"] is original.confidence is None
        assert set(actual["sourceTokenIds"]) <= set(registry.values())
        assert original.field_id not in raw.decode()
    assert output.receipt_id not in raw.decode()
    assert evidence.gate_result.gate_result_id not in raw.decode()
    for token in source.tokens:
        assert token.token_id not in raw.decode()


def test_deterministic_exact_bytes_and_public_validator_receives_same_bytes():
    source, evidence, _ = prepare()
    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2, \
         patch.object(projection, "decode_and_validate_presentation_v1", wraps=decode_and_validate_presentation_v1) as check:
        first = emit(source, evidence)
        second = emit(source, evidence)
    assert b2.call_count == check.call_count == 2
    assert first == second
    assert check.call_args.args[0] is second
    assert check.call_args.kwargs == dict(expected_request_id=REQUEST, expected_image_id=IMAGE, consumer_mode="FIXTURE")
    assert first == json.dumps(json.loads(first), sort_keys=True, ensure_ascii=True,
                               allow_nan=False, separators=(",", ":")).encode("utf-8")
    assert not first.startswith(b"\xef\xbb\xbf")
    assert first.endswith(b"}") and b"fixtureStatus" not in first


@pytest.mark.parametrize("argument,value,code", [
    ("request", "request-other", "REJECT_REQUEST_ID_MISMATCH"),
    ("image", "image-other", "REJECT_IMAGE_ID_MISMATCH"),
    ("mode", "LIVE", "REJECT_SOURCE_MODE_MISMATCH"),
])
def test_independent_consumer_context_rejects_valid_emitted_bytes(argument, value, code):
    source, evidence, _ = prepare()
    raw = emit(source, evidence)
    with pytest.raises(ConformanceViolation) as caught:
        validated(raw, **{argument: value})
    assert caught.value.code == code


@pytest.mark.parametrize("changes", [
    {"consumer_mode": "LIVE"}, {"consumer_mode": "fixture"},
    {"request_id": "file:///tmp/SECRET"}, {"request_id": "participant-001"},
    {"request_id": ""}, {"request_id": "request\n"}, {"request_id": "请求"},
    {"image_id": "image-other"}, {"image_id": "C:\\private\\SECRET.jpg"},
    {"producer_id": "annotation-001"}, {"producer_id": ""},
    {"alias_namespace": "a" * 31}, {"alias_namespace": "a" * 33},
    {"alias_namespace": "A" * 32}, {"alias_namespace": "g" * 32},
    {"alias_namespace": "a" * 32 + "\n"}, {"alias_namespace": None},
])
def test_invalid_context_rejected_before_b2_with_safe_diagnostics(changes):
    source, evidence, _ = prepare()
    with patch.object(projection, "extract_b2") as b2:
        with pytest.raises(ValueError) as caught:
            emit(source, evidence, **changes)
    b2.assert_not_called()
    assert_safe_failure(caught.value)


@pytest.mark.parametrize("fault", [
    "tokens_copy", "provenance_copy", "receipt", "gate_receipt", "processing",
    "decision_string", "status_string", "duplicate_token", "token_owner", "geometry",
])
def test_invalidated_or_substituted_source_rejected_before_b2(fault):
    source, evidence, _ = prepare()
    if fault == "tokens_copy":
        evidence = replace(evidence, tokens=tuple(list(source.tokens)))
        assert evidence.tokens is not source.tokens
    elif fault == "provenance_copy":
        evidence = replace(evidence, provenance=replace(source.provenance))
    elif fault == "receipt":
        object.__setattr__(evidence, "receipt_id", "foreign:receipt")
    elif fault == "gate_receipt":
        object.__setattr__(evidence.gate_result, "receipt_id", "foreign:receipt")
    elif fault == "processing":
        object.__setattr__(evidence, "processing_status", SourceProcessingStatus.OCR_PARTIAL)
    elif fault == "decision_string":
        object.__setattr__(evidence.gate_result, "decision", "INSUFFICIENT")
    elif fault == "status_string":
        object.__setattr__(source, "processing_status", "OCR_COMPLETED")
        object.__setattr__(evidence, "processing_status", "OCR_COMPLETED")
    elif fault == "duplicate_token":
        duplicated = (source.tokens[0], source.tokens[0])
        object.__setattr__(source, "tokens", duplicated)
        object.__setattr__(evidence, "tokens", duplicated)
    elif fault == "token_owner":
        object.__setattr__(source.tokens[0], "receipt_id", "foreign:receipt")
    else:
        object.__setattr__(source.tokens[0].polygon[0], "x", float("nan"))
    with patch.object(projection, "extract_b2") as b2:
        with pytest.raises(ValueError) as caught:
            emit(source, evidence)
    b2.assert_not_called()
    assert_safe_failure(caught.value)


@pytest.mark.parametrize("fault", [
    "evidence_copy", "field_duplicate", "row_duplicate", "unknown_token", "field_owner",
    "row_owner", "stage", "extraction_enum", "field_enum", "field_confidence", "missing_value",
])
def test_reject_invalidated_actual_b2_results_without_hiding_bad_identities(fault):
    """Negative probes deliberately invalidate a real result, not fake B2 successes."""
    source, evidence, _ = prepare()

    def invalidated(actual_evidence):
        result = real_extract_b2(actual_evidence)
        output = result.receipt_output
        if fault == "evidence_copy":
            object.__setattr__(output, "source_evidence", replace(actual_evidence))
        elif fault == "field_duplicate":
            object.__setattr__(output.purchase_date, "field_id", output.store_name.field_id)
        elif fault == "row_duplicate":
            duplicate = output.items[0].row_id
            object.__setattr__(output.items[1], "row_id", duplicate)
            for field in output.items[1].fields:
                object.__setattr__(field, "item_row_id", duplicate)
        elif fault == "unknown_token":
            object.__setattr__(output.store_name, "source_token_ids", ("SECRET:unknown:token",))
        elif fault == "field_owner":
            object.__setattr__(output.store_name, "receipt_id", "foreign:receipt")
        elif fault == "row_owner":
            object.__setattr__(output.items[0].quantity, "item_row_id", "foreign:row")
        elif fault == "stage":
            object.__setattr__(output, "output_stage", OutputStage.HUMAN_REVIEWED)
        elif fault == "extraction_enum":
            object.__setattr__(output, "extraction_status", "EXTRACTED")
        elif fault == "field_enum":
            object.__setattr__(output.store_name, "status", "EXTRACTED")
        elif fault == "field_confidence":
            object.__setattr__(output.store_name, "confidence", True)
        else:
            object.__setattr__(output.store_name, "status", FieldStatus.MISSING)
            object.__setattr__(output.store_name, "unresolved_reason", "Not observed.")
        return result

    with patch.object(projection, "extract_b2", side_effect=invalidated) as b2:
        with pytest.raises(ValueError) as caught:
            emit(source, evidence)
    b2.assert_called_once_with(evidence)
    assert_safe_failure(caught.value)


def test_foreign_equal_fallback_gate_is_rejected():
    source, evidence, _ = prepare(decision=SourceEvidenceDecision.INSUFFICIENT)

    def invalidated(actual_evidence):
        result = real_extract_b2(actual_evidence)
        object.__setattr__(result.pre_resolution_disposition, "gate_result", replace(actual_evidence.gate_result))
        return result

    with patch.object(projection, "extract_b2", side_effect=invalidated) as b2:
        with pytest.raises(ValueError):
            emit(source, evidence)
    b2.assert_called_once_with(evidence)


@pytest.mark.parametrize("options,role,value,code", [
    ({"date": "13/10/2026"}, "PURCHASE_DATE", "13/10/2026", "REJECT_INVALID_DATE"),
    ({"quantity": "0"}, "QUANTITY", "0", "REJECT_INVALID_QUANTITY"),
    ({"quantity": "01"}, "QUANTITY", "01", "REJECT_INVALID_QUANTITY"),
    ({"quantity": "1.0000"}, "QUANTITY", "1.0000", "REJECT_INVALID_QUANTITY"),
    ({"unit": "$5.50"}, "UNIT_PRICE", "$5.50", "REJECT_CURRENCY_MISMATCH"),
    ({"unit": "RM 01.00"}, "UNIT_PRICE", "RM 01.00", "REJECT_VALUE_RELATIONSHIP"),
])
def test_nonrepresentable_values_are_genuinely_extracted_then_rejected(options, role, value, code):
    source, evidence, _ = prepare(**options)
    before = repr((source, evidence))
    captured, execute = capture_real_results()
    with patch.object(projection, "extract_b2", side_effect=execute) as b2:
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    output = captured[0].receipt_output
    fields = (output.purchase_date,) + output.items[0].fields
    field = next(field for field in fields if field.field_name.value == role)
    assert field.status is FieldStatus.EXTRACTED and field.value == value
    assert caught.value.code == code
    if role == "UNIT_PRICE":
        # Money projection can fail before a complete envelope exists. Its
        # genuine indexed path must still be bound to the validated B2 records.
        assert caught.value.path == "$.receipt.itemRows[0].fields[2].originalAutomaticValue"
    assert before == repr((source, evidence))
    b2.assert_called_once_with(evidence)
    assert_safe_failure(caught.value)


def test_weighted_quantity_and_myr_normalization_preserve_genuine_originals():
    source, evidence, _ = prepare(quantity="0.750", unit="RM 1,234.50", receipt_total="MYR 23.90")
    raw = emit(source, evidence)
    wire = json.loads(raw)
    fields = wire["receipt"]["itemRows"][0]["fields"]
    assert fields[1]["originalAutomaticValue"] == fields[1]["presentationValue"] == "0.750"
    assert fields[2]["originalAutomaticValue"] == "RM 1,234.50"
    assert fields[2]["presentationValue"] == "1234.50"
    assert wire["receipt"]["receiptFields"][2]["originalAutomaticValue"] == "MYR 23.90"
    assert wire["receipt"]["receiptFields"][2]["presentationValue"] == "23.90"
    validated(raw)


def test_missing_and_unresolved_fields_keep_null_values_reasons_and_references():
    source, evidence, _ = prepare(date="02/03/2026", partial=True, no_store=True)
    wire = json.loads(emit(source, evidence))
    store, date = wire["receipt"]["receiptFields"][:2]
    assert store["status"] == "MISSING"
    assert date["status"] == "UNRESOLVED" and date["sourceTokenIds"]
    assert wire["receipt"]["itemRows"][0]["fields"][1]["status"] == "MISSING"
    assert wire["receipt"]["itemRows"][0]["fields"][2]["status"] == "MISSING"
    for field in (store, date, *wire["receipt"]["itemRows"][0]["fields"][1:3]):
        assert field["originalAutomaticValue"] is field["presentationValue"] is field["nativeConfidence"] is None
        assert field["absenceReason"]


def test_metadata_redaction_and_no_external_processing_side_effects(capsys):
    source, evidence, _ = prepare()
    with patch("builtins.open", side_effect=AssertionError("filesystem")), \
         patch("pathlib.Path.open", side_effect=AssertionError("filesystem")), \
         patch("os.open", side_effect=AssertionError("filesystem")), \
         patch("socket.socket", side_effect=AssertionError("network")), \
         patch("subprocess.Popen", side_effect=AssertionError("process")):
        raw = emit(source, evidence)
    wire = json.loads(raw)
    assert wire["source"] == {"type": "SYNTHETIC_FIXTURE", "provenance": {
        "sourceSystem": "I2B_SYNTHETIC_B2_V0", "sourceReference": f"src-v1-{NAMESPACE}-1",
        "contentSha256": None,
    }}
    for secret in (evidence.provenance.source_system, evidence.provenance.source_reference,
                   "original_text", "polygon", "raw_confidence", "alias_registry"):
        assert secret not in raw.decode()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("reason", ["file:///tmp/participant-001.jpg", "OCR:failed", "path=/tmp/SECRET.jpg"])
def test_unsafe_recorded_gate_reasons_fail_without_post_insufficient_error_envelope(reason):
    source, evidence, _ = prepare(decision=SourceEvidenceDecision.INSUFFICIENT, reasons=(reason,))
    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2:
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    b2.assert_called_once_with(evidence)
    assert caught.value.code == "REJECT_UNSAFE_PROVENANCE"
    assert caught.value.path == "$.sourceGate.reasons[0]"
    assert_safe_failure(caught.value)


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("literal", ["PANTRYPROOF TEST MART", "2026-10-13", "MILK", "x", "1"])
def test_source_aware_gate_reason_rejects_complete_literal_ocr_transcription(decision, literal):
    source, evidence, evaluator = prepare(decision=decision, reasons=(literal,))
    assert literal in {token.original_text for token in source.tokens}
    before = repr((source, evidence))
    accepted = []

    def record_existing_validation(raw, **context):
        dto = decode_and_validate_presentation_v1(raw, **context)
        accepted.append(dto)
        return dto

    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2, \
         patch.object(projection, "decode_and_validate_presentation_v1", side_effect=record_existing_validation):
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    # Existing schema validation accepts these values; only the new check has
    # access to the actual OCR text. Its failure must not expose that text.
    assert len(accepted) == 1 and accepted[0].source_gate.reasons == (literal,)
    assert caught.value.code == "REJECT_UNSAFE_PROVENANCE"
    assert caught.value.path == "$.sourceGate.reasons[0]"
    assert caught.value.detail == "Synthetic projection rejected."
    assert_safe_failure(caught.value)
    b2.assert_called_once_with(evidence)
    evaluator.assert_called_once_with(source)
    assert before == repr((source, evidence))


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
def test_source_aware_gate_reason_preserves_order_and_rejects_later_leak(decision):
    reasons = ("Synthetic source structure was unavailable.", "PANTRYPROOF TEST MART")
    source, evidence, _ = prepare(decision=decision, reasons=reasons)
    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2:
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    assert caught.value.code == "REJECT_UNSAFE_PROVENANCE"
    assert caught.value.path == "$.sourceGate.reasons[1]"
    assert evidence.gate_result.reasons == reasons
    b2.assert_called_once_with(evidence)
    assert_safe_failure(caught.value)


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("reason", [
    "There is 1 unreadable row.",
    "The x marker was unavailable.",
    "Extraction could not locate 1 safe heading.",
    "Synthetic source structure was unavailable.",
])
def test_source_aware_gate_reason_preserves_safe_prose_and_short_token_collisions(decision, reason):
    source, evidence, _ = prepare(decision=decision, reasons=(reason,))
    assert {"1", "x"} <= {token.original_text for token in source.tokens}
    before = repr((source, evidence))
    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2:
        raw = emit(source, evidence)
    dto = validated(raw)
    assert dto.source_gate.reasons == (reason,)
    expected = "RESULT_AVAILABLE" if decision is SourceEvidenceDecision.SUFFICIENT else "SOURCE_EVIDENCE_INSUFFICIENT"
    assert dto.outcome.status == expected
    if decision is SourceEvidenceDecision.INSUFFICIENT:
        assert dto.receipt is dto.automatic_extraction is dto.outcome.failure is None
    b2.assert_called_once_with(evidence)
    assert before == repr((source, evidence))


def test_source_aware_gate_reason_preserves_existing_v1_rejection_precedence():
    source, evidence, _ = prepare(date="13/10/2026", reasons=("PANTRYPROOF TEST MART",))
    with pytest.raises(ConformanceViolation) as caught:
        emit(source, evidence)
    assert caught.value.code == "REJECT_INVALID_DATE"
    assert caught.value.path == "$.receipt.receiptFields[1].presentationValue"


@pytest.mark.parametrize("reason", ["", " \t\r\n"])
def test_blank_gate_reasons_retain_existing_v1_gate_state_classification(reason):
    source, evidence, _ = prepare(decision=SourceEvidenceDecision.INSUFFICIENT, reasons=(reason,))
    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2:
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    b2.assert_called_once_with(evidence)
    assert caught.value.code == "REJECT_GATE_STATE"
    assert caught.value.path == "$.sourceGate.reasons[0]"


def test_gate_reason_uses_existing_v1_nonblank_rule_without_unicode_stripping():
    # V1's four-character blank set deliberately differs from str.strip().
    reason = "\u00a0"
    source, evidence, _ = prepare(decision=SourceEvidenceDecision.INSUFFICIENT, reasons=(reason,))
    accepted = []

    def record_existing_validation(raw, **context):
        dto = decode_and_validate_presentation_v1(raw, **context)
        accepted.append(dto)
        return dto

    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2, \
         patch.object(projection, "decode_and_validate_presentation_v1", side_effect=record_existing_validation):
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    assert len(accepted) == 1 and accepted[0].source_gate.reasons == (reason,)
    assert caught.value.code == "REJECT_UNSAFE_PROVENANCE"
    assert caught.value.path == "$.sourceGate.reasons[0]"
    assert_safe_failure(caught.value)
    b2.assert_called_once_with(evidence)
    assert evidence.gate_result.reasons == (reason,)


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError, TypeError])
def test_b2_failure_propagates_as_safe_failure_without_retry_or_partial_output(error_type, capsys):
    source, evidence, _ = prepare()
    with patch.object(projection, "extract_b2", side_effect=error_type("SECRET file:///tmp/participant-001.jpg")) as b2:
        with pytest.raises(RuntimeError) as caught:
            emit(source, evidence)
    b2.assert_called_once_with(evidence)
    assert str(caught.value) == "Synthetic B2 execution failed."
    assert_safe_failure(caught.value)
    assert capsys.readouterr() == ("", "")


def test_final_validation_failure_does_not_return_bytes_or_publish_private_details():
    source, evidence, _ = prepare()
    with patch.object(projection, "decode_and_validate_presentation_v1", side_effect=ConformanceViolation(
        "REJECT_INVALID_JSON", "$", "SECRET private:receipt file:///tmp/participant-001.jpg",
    )):
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    assert caught.value.code == "REJECT_INVALID_JSON" and caught.value.path == "$"
    assert_safe_failure(caught.value)


def test_existing_fixture_bytes_lengths_and_expectations_are_preserved():
    raw = (ROOT / "manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "4b1bcd3445d82852c7f4c3beb5f0e07f39853497e92713b81a063dcdf5350ee9"
    entries = json.loads(raw)["fixtures"]
    assert len(entries) == len({entry["path"] for entry in entries}) == 32
    assert sum(entry["expectedResult"] == "ACCEPT" for entry in entries) == 17
    assert sum(entry["expectedResult"].startswith("REJECT_") for entry in entries) == 15
    for entry in entries:
        payload = (ROOT / entry["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert len(payload) == entry["byteLength"]


def test_public_signature_and_production_dependency_boundary():
    signature = inspect.signature(projection.extract_b2_fixture_presentation_v1)
    assert list(signature.parameters) == ["adapted_source", "source_evidence", "request_id", "image_id",
                                          "alias_namespace", "producer_id", "consumer_mode"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is inspect.Parameter.empty
               for p in signature.parameters.values())
    imports = [node.module or "" for node in ast.walk(ast.parse(inspect.getsource(projection)))
               if isinstance(node, ast.ImportFrom)]
    assert all(not module.startswith(("tests", "pipeline.proposed", "pipeline.backend_receipt_execution"))
               for module in imports)
    assert "attach_gate_result" not in vars(projection)
    assert "extract_adapted_receipt_v0" not in vars(projection)


# Independent reviewed literals: these tests do not obtain admission policy
# or path grammar from the implementation under test.
APPROVED_REASONS = (
    "Synthetic source structure was unavailable.",
    "There is 1 unreadable row.",
    "The x marker was unavailable.",
    "Extraction could not locate 1 safe heading.",
)
APPROVED_CODES = tuple("""
REJECT_CONTRADICTORY_FIELD_STATE REJECT_CURRENCY_METADATA REJECT_CURRENCY_MISMATCH
REJECT_DUPLICATE_FIELD_ID REJECT_DUPLICATE_JSON_KEY REJECT_DUPLICATE_ROW_ID
REJECT_DUPLICATE_TOKEN_ID REJECT_DUPLICATE_TOKEN_REFERENCE REJECT_EVIDENCE_STAGE_MISMATCH
REJECT_GATE_OUTCOME_MISMATCH REJECT_GATE_STATE REJECT_IMAGE_ID_MISMATCH
REJECT_INVALID_CONFIDENCE REJECT_INVALID_DATE REJECT_INVALID_DIGEST REJECT_INVALID_ID
REJECT_INVALID_JSON REJECT_INVALID_MONEY REJECT_INVALID_QUANTITY REJECT_MISSING_MEMBER
REJECT_OUTCOME_STAGE_MISMATCH REJECT_OUTCOME_STATE_MISMATCH REJECT_PRODUCER_METADATA
REJECT_REQUEST_ID_MISMATCH REJECT_ROLE_ORDER REJECT_ROLE_SET REJECT_SOURCE_MODE_MISMATCH
REJECT_TOKEN_INTEGRITY REJECT_UNKNOWN_ENUM REJECT_UNKNOWN_MEMBER REJECT_UNKNOWN_ROLE
REJECT_UNKNOWN_TOKEN_REFERENCE REJECT_UNSAFE_PROVENANCE
REJECT_UNSUPPORTED_CONTRACT_VERSION REJECT_UNSUPPORTED_SCHEMA_VERSION REJECT_VALUE_RELATIONSHIP
""".split())


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("reason", [
    "Unable to read MILK during capture.", "Unreadable PANTRYPROOF heading.",
    "Unable to read milk during capture.", "Synthetic source structure was unavailable. ",
    "synthetic source structure was unavailable.", "There is 2 unreadable row.",
    "A generic explanation not in the approved vocabulary.",
])
def test_j04_unapproved_embedded_partial_transformed_and_generic_reasons(decision, reason):
    source, evidence, evaluator = prepare(decision=decision, reasons=(reason,))
    before = repr((source, evidence))
    validated_before_admission = []

    def validate_first(raw, **context):
        validated_before_admission.append(decode_and_validate_presentation_v1(raw, **context))

    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2, \
         patch.object(projection, "decode_and_validate_presentation_v1", side_effect=validate_first):
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    assert len(validated_before_admission) == 1
    assert caught.value.code == "REJECT_UNSAFE_PROVENANCE"
    assert caught.value.path == "$.sourceGate.reasons[0]"
    assert caught.value.detail == "Synthetic projection rejected."
    assert_safe_failure(caught.value)
    b2.assert_called_once_with(evidence)
    evaluator.assert_called_once_with(source)
    assert before == repr((source, evidence))


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("reason", APPROVED_REASONS)
def test_j04_approved_phrase_equal_to_complete_ocr_token_is_still_rejected(decision, reason):
    source, evidence, _ = prepare(decision=decision, reasons=(reason,))
    tokens = (replace(source.tokens[0], original_text=reason),) + source.tokens[1:]
    source = replace(source, tokens=tokens)
    evidence = replace(evidence, tokens=tokens)
    before = repr((source, evidence))
    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2:
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    assert caught.value.code == "REJECT_UNSAFE_PROVENANCE"
    assert caught.value.path == "$.sourceGate.reasons[0]"
    b2.assert_called_once_with(evidence)
    assert before == repr((source, evidence))


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
def test_j04_multiple_approved_reasons_and_first_rejected_index(decision):
    source, evidence, _ = prepare(decision=decision, reasons=APPROVED_REASONS)
    before = repr((source, evidence))
    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2:
        assert validated(emit(source, evidence)).source_gate.reasons == APPROVED_REASONS
    b2.assert_called_once_with(evidence)
    assert before == repr((source, evidence))
    reasons = APPROVED_REASONS[:2] + ("Unapproved generic explanation.", "MILK")
    source, evidence, _ = prepare(decision=decision, reasons=reasons)
    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2:
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    assert caught.value.code == "REJECT_UNSAFE_PROVENANCE"
    assert caught.value.path == "$.sourceGate.reasons[2]"
    assert evidence.gate_result.reasons == reasons
    b2.assert_called_once_with(evidence)


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("reason", [APPROVED_REASONS[0], "MILK", "file:///tmp/participant-001.jpg"])
def test_j04_duplicate_reasons_keep_existing_gate_state_precedence(decision, reason):
    # Duplicates cannot form a genuine V0 gate. Verify that earlier boundary,
    # then inject a duplicate only into the wire projection of a real B2 call.
    with pytest.raises(ValueError, match="reasons must not contain duplicates"):
        prepare(decision=decision, reasons=(reason, reason))
    source, evidence, _ = prepare(decision=decision, reasons=(reason,))
    before = repr((source, evidence))
    real_envelope = projection._envelope

    def duplicate_wire_reasons(*args):
        envelope = real_envelope(*args)
        envelope["sourceGate"]["reasons"] = [reason, reason]
        return envelope

    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2, \
         patch.object(projection, "_envelope", side_effect=duplicate_wire_reasons):
        with pytest.raises(ConformanceViolation) as caught:
            emit(source, evidence)
    assert caught.value.code == "REJECT_GATE_STATE"
    assert caught.value.path == "$.sourceGate.reasons[1]"
    b2.assert_called_once_with(evidence)
    assert_safe_failure(caught.value)
    assert before == repr((source, evidence))


def diagnostic_failure(error, *, decision=SourceEvidenceDecision.SUFFICIENT, prepare_options=None):
    """Inject only the exception; B2 and the preceding decoder are genuine."""
    source, evidence, _ = prepare(decision=decision, reasons=APPROVED_REASONS[:2], **(prepare_options or {}))
    before = repr((source, evidence))

    def validate_then_raise(raw, **context):
        decode_and_validate_presentation_v1(raw, **context)
        raise error

    with patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2, \
         patch.object(projection, "decode_and_validate_presentation_v1", side_effect=validate_then_raise):
        with pytest.raises(Exception) as caught:
            emit(source, evidence)
    b2.assert_called_once_with(evidence)
    assert before == repr((source, evidence))
    assert_safe_failure(caught.value)
    return caught.value


@pytest.mark.parametrize("code", APPROVED_CODES)
def test_j04_all_36_diagnostic_codes_are_preserved_without_private_detail(code):
    assert len(APPROVED_CODES) == len(set(APPROVED_CODES)) == 36
    error = diagnostic_failure(ConformanceViolation(code, "$", "SECRET MILK file:///tmp/participant-001.jpg"))
    assert type(error) is ConformanceViolation
    assert (error.code, error.path, error.detail) == (code, "$", "Synthetic projection rejected.")
    assert "MILK" not in str(error)


SCALAR_PATHS = (
    "$", "$context.mode", "$context.expectedRequestId", "$context.expectedImageId",
    "$.schemaName", "$.schemaVersion", "$.sourceContractVersion", "$.requestId", "$.imageId",
    "$.source", "$.source.type", "$.source.provenance", "$.source.provenance.sourceSystem",
    "$.source.provenance.sourceReference", "$.source.provenance.contentSha256",
    "$.outcome", "$.outcome.status", "$.outcome.failure", "$.outcome.failure.stage",
    "$.outcome.failure.code", "$.outcome.failure.retryable", "$.sourceEvidence",
    "$.sourceEvidence.sourceProcessingStatus", "$.sourceEvidence.tokenIds",
    "$.sourceGate", "$.sourceGate.gateResultId", "$.sourceGate.decision", "$.sourceGate.reasons",
    "$.automaticExtraction", "$.automaticExtraction.stage", "$.automaticExtraction.extractionStatus",
    "$.automaticExtraction.producer", "$.automaticExtraction.producer.producerId",
    "$.automaticExtraction.producer.producerVersion", "$.receipt", "$.receipt.receiptId",
    "$.receipt.currencyCode", "$.receipt.receiptFields", "$.receipt.itemRows",
    "$.receipt.itemRows[0]", "$.receipt.itemRows[1].rowId", "$.receipt.itemRows[1].fields",
)
FIELD_MEMBERS = (
    "fieldId", "role", "status", "originalAutomaticValue", "presentationValue",
    "absenceReason", "sourceTokenIds", "nativeConfidence",
)
VALID_PATHS = SCALAR_PATHS + (
    "$.sourceGate.reasons[0]", "$.sourceGate.reasons[1]", "$.sourceEvidence.tokenIds[0]",
    "$.sourceEvidence.tokenIds[10]", "$.receipt.receiptFields[2]",
    "$.receipt.itemRows[1].fields[3]", "$.receipt.itemRows[0].fields[0].sourceTokenIds[0]",
    "$.receipt.receiptFields[0].sourceTokenIds[0]",
) + tuple(f"{parent}.{member}" for parent in (
    "$.receipt.receiptFields[1]", "$.receipt.itemRows[1].fields[2]",
) for member in FIELD_MEMBERS)


@pytest.mark.parametrize("path", VALID_PATHS)
def test_j04_known_structural_and_context_paths_are_preserved(path):
    error = diagnostic_failure(ConformanceViolation("REJECT_INVALID_JSON", path, "SECRET"))
    assert type(error) is ConformanceViolation
    assert error.path == path and error.code == "REJECT_INVALID_JSON"
    assert error.detail == "Synthetic projection rejected."


@pytest.mark.parametrize("path", [
    "", "$context", "$context.SECRET", "$context.mode.SECRET", "$context.requestId",
    "$.SECRET", "$.sourceGate.SECRET", "$.receipt.sourceGate", "$.receipt.currencyCode.bad",
    "$.sourceGate.reasons[2]", "$.sourceEvidence.tokenIds[999]", "$.receipt.receiptFields[3]",
    "$.receipt.itemRows[2]", "$.receipt.itemRows[0].fields[4]",
    "$.receipt.itemRows[0].fields[0].sourceTokenIds[1]",
    "$.receipt.itemRows.fields[0]", "$.sourceGate[0]", "$.sourceGate..reasons",
    "$.sourceGate.reasons[]", "$.sourceGate.reasons[-1]", "$.sourceGate.reasons[+0]",
    "$.sourceGate.reasons[00]", "$.sourceGate.reasons[01]", "$.sourceGate.reasons[ 0]",
    "$.sourceGate.reasons[\u0660]", "$.sourceGate.reasons[\uff10]", "$.sourceGate.reasons[0.0]",
    "$.sourceGate.reasons[1e0]", "$.sourceGate.reasons[*]", "$['sourceGate']",
    "$.sourceGate.reasons[0].MILK", "$.sourceGate.reasons[0]file:///tmp/participant-001.jpg",
    "$.sourceGate.reasons[0]\n", "$.sourceGate.reasons[" + "9" * 5000 + "]",
    "$.sourceGate.reasons[0][0]", "$.sourceGate.reasons[0].", "$.sourceGate.reasons[0]\x00",
])
def test_j04_unknown_private_noncanonical_and_out_of_bounds_paths_fail_closed(path):
    error = diagnostic_failure(ConformanceViolation("REJECT_INVALID_JSON", path, "SECRET"))
    assert type(error) is RuntimeError
    assert error.args == ("Synthetic projection failed.",)


@pytest.mark.parametrize("options,path", [
    ({"empty": True}, "$.sourceEvidence.tokenIds[0]"),
    ({"empty": True}, "$.receipt.itemRows[0].rowId"),
    ({"no_store": True}, "$.receipt.receiptFields[0].sourceTokenIds[0]"),
])
def test_j04_bounds_follow_actual_empty_and_nested_arrays(options, path):
    error = diagnostic_failure(ConformanceViolation("REJECT_INVALID_JSON", path, "SECRET"), prepare_options=options)
    assert type(error) is RuntimeError and str(error) == "Synthetic projection failed."


def test_j04_insufficient_result_has_no_receipt_array_bounds():
    error = diagnostic_failure(ConformanceViolation(
        "REJECT_INVALID_JSON", "$.receipt.receiptFields[0].fieldId", "SECRET",
    ), decision=SourceEvidenceDecision.INSUFFICIENT)
    assert type(error) is RuntimeError and str(error) == "Synthetic projection failed."


@pytest.mark.parametrize("array,path", [
    ("reasons", "$.sourceGate.reasons[1]"),
    ("rows", "$.receipt.itemRows[1].rowId"),
])
def test_j04_final_diagnostic_bounds_follow_actual_envelope_not_only_b2(array, path):
    real_envelope = projection._envelope

    def shorten_array(*args):
        envelope = real_envelope(*args)
        if array == "reasons":
            envelope["sourceGate"]["reasons"] = envelope["sourceGate"]["reasons"][:1]
        else:
            envelope["receipt"]["itemRows"] = envelope["receipt"]["itemRows"][:1]
        return envelope

    with patch.object(projection, "_envelope", side_effect=shorten_array):
        error = diagnostic_failure(ConformanceViolation("REJECT_INVALID_JSON", path, "SECRET"))
    assert type(error) is RuntimeError and str(error) == "Synthetic projection failed."


def test_j04_indexed_metadata_without_independently_verified_bounds_fails_closed():
    source, evidence, _ = prepare()
    with patch.object(projection, "_validate_result", side_effect=ConformanceViolation(
        "REJECT_INVALID_JSON", "$.receipt.receiptFields[0].fieldId", "SECRET",
    )), patch.object(projection, "extract_b2", wraps=real_extract_b2) as b2:
        with pytest.raises(RuntimeError) as caught:
            emit(source, evidence)
    b2.assert_called_once_with(evidence)
    assert str(caught.value) == "Synthetic projection failed."
    assert_safe_failure(caught.value)


class HostileDiagnosticValue:
    def __str__(self):
        raise AssertionError("must not format untrusted metadata")

    def __repr__(self):
        raise AssertionError("must not represent untrusted metadata")


class DiagnosticString(str):
    pass


@pytest.mark.parametrize("member,value", [
    ("code", "REJECT_SECRET"), ("code", "REJECT_INVALID_JSON\n"),
    ("code", "MILK file:///tmp/participant-001.jpg"),
    ("code", DiagnosticString("REJECT_INVALID_JSON")), ("code", None),
    ("code", 123), ("code", HostileDiagnosticValue()),
    ("path", DiagnosticString("$")), ("path", None), ("path", 123),
    ("path", HostileDiagnosticValue()), ("code", ["REJECT_INVALID_JSON"]),
], ids=[f"metadata-{i}" for i in range(12)])
def test_j04_diagnostic_exact_types_and_code_membership(member, value):
    original = ConformanceViolation("REJECT_INVALID_JSON", "$", "SECRET")
    setattr(original, member, value)
    error = diagnostic_failure(original)
    assert type(error) is RuntimeError and error.args == ("Synthetic projection failed.",)


def test_j04_conformance_subclass_is_not_admitted():
    class ForeignViolation(ConformanceViolation):
        pass

    error = diagnostic_failure(ForeignViolation("REJECT_INVALID_JSON", "$", "SECRET"))
    assert type(error) is RuntimeError and str(error) == "Synthetic projection failed."


def test_j04_untrusted_detail_is_discarded_without_formatting():
    original = ConformanceViolation("REJECT_INVALID_JSON", "$", "SECRET")
    original.detail = HostileDiagnosticValue()
    error = diagnostic_failure(original)
    assert type(error) is ConformanceViolation and error.detail == "Synthetic projection rejected."


@pytest.mark.parametrize("safe_metadata", [True, False])
def test_j04_original_detail_causes_contexts_and_notes_are_never_published(safe_metadata, capsys):
    try:
        raise ValueError("SECRET MILK file:///tmp/participant-001.jpg")
    except ValueError as cause:
        try:
            raise ConformanceViolation(
                "REJECT_INVALID_JSON" if safe_metadata else "REJECT_SECRET", "$", "SECRET MILK",
            ) from cause
        except ConformanceViolation as caught:
            original = caught
    original.add_note("SECRET private:receipt:synthetic-alpha")
    assert original.__cause__ is not None and original.__context__ is not None
    error = diagnostic_failure(original)
    assert error is not original and not getattr(error, "__notes__", ())
    assert "MILK" not in "".join(traceback.format_exception(error))
    assert capsys.readouterr() == ("", "")
    if safe_metadata:
        assert type(error) is ConformanceViolation
        assert error.args == ("REJECT_INVALID_JSON at $: Synthetic projection rejected.",)
    else:
        assert type(error) is RuntimeError and error.args == ("Synthetic projection failed.",)
