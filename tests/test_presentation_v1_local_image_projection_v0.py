"""T08 structural checks using in-memory records and test-only gate approvals."""

from dataclasses import replace
import json
from unittest.mock import patch

import pytest

from pipeline import ocr_adapter
from pipeline.contracts import (
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
)
from pipeline.gate_c_source_gate_v0 import GATE_C_SOURCE_GATE_V0
from pipeline.layout_b2 import extract_b2
from pipeline.presentation_v1 import b2_synthetic_projection_v0 as fixture_projection
from pipeline.presentation_v1.conformance import decode_and_validate_presentation_v1
from pipeline.presentation_v1.local_image_projection_v0 import (
    LOCAL_IMAGE_SOURCE_SYSTEM,
    LiveGateApprovalV0,
    LocalImageFailureV0,
    LocalImagePresentationContextV0,
    LocalImageProjectionError,
    RetainedLiveGateV0,
    RetainedLocalImageAttemptV0,
    project_retained_local_image_presentation_v1,
)


REASON = "Receipt structure was unavailable."


@pytest.fixture
def context():
    return LocalImagePresentationContextV0(
        request_id="request-local-ordinary",
        image_id="image-local-ordinary",
        receipt_id="receipt-retained-ordinary",
        alias_namespace="0123456789abcdef0123456789abcdef",
        approved_gate=LiveGateApprovalV0("test-policy", "test-v1", "a" * 64, (REASON,)),
    )


def _adapt(context, *, store="TEST MART", source_system=LOCAL_IMAGE_SOURCE_SYSTEM):
    regions = [
        (store, 20, 0, 180),
        ("DATE:", 10, 20, 45),
        ("2026-10-13", 70, 20, 100),
        ("MILK", 10, 45, 45),
        ("2", 110, 45, 10),
        ("x", 130, 45, 8),
        ("5.50", 155, 45, 38),
        ("11.00", 220, 45, 45),
        ("TOTAL", 130, 95, 55),
        ("11.00", 220, 95, 70),
    ]
    return ocr_adapter.adapt_paddleocr_result(
        {
            "rec_texts": [text for text, *_ in regions],
            "rec_boxes": [[x, y, x + width, y + 10] for _, x, y, width in regions],
        },
        receipt_id=context.receipt_id,
        image_id=context.image_id,
        source_system=source_system,
        source_reference=context.source_reference,
        processing_status=SourceProcessingStatus.OCR_COMPLETED,
    )


def _retained(
    context, *, decision=SourceEvidenceDecision.SUFFICIENT, reason=REASON, **source_options,
):
    source = _adapt(context, **source_options)
    gate = SourceEvidenceGateResult(
        "private:gate:record", context.receipt_id, decision,
        (reason,) if decision is SourceEvidenceDecision.INSUFFICIENT else (),
    )
    evidence = ocr_adapter.attach_gate_result(source, gate)
    return RetainedLocalImageAttemptV0(
        context.request_id,
        context.image_id,
        adapted_source=source,
        gate=RetainedLiveGateV0(context.approved_gate, source, gate),
        source_evidence=evidence,
        b2_result=extract_b2(evidence),
    )


def _emit(context, attempt):
    return project_retained_local_image_presentation_v1(context=context, attempt=attempt)


def _decode(context, raw):
    return decode_and_validate_presentation_v1(
        raw,
        expected_request_id=context.request_id,
        expected_image_id=context.image_id,
        consumer_mode="LIVE",
    )


@pytest.mark.parametrize("store", ["SUNNY MART", "RAINY GROCER"])
def test_reviewable_result_retains_dynamic_b2_values_and_aliases(context, store):
    attempt = _retained(context, store=store)
    output = attempt.b2_result.receipt_output
    with (
        patch.object(ocr_adapter, "attach_gate_result") as attach,
        patch.object(fixture_projection, "extract_b2") as extract,
        patch.object(fixture_projection, "project_retained_b2_fixture_presentation_v1") as fixture,
    ):
        raw = _emit(context, attempt)
        assert _emit(context, attempt) == raw
    attach.assert_not_called()
    extract.assert_not_called()
    fixture.assert_not_called()
    dto = _decode(context, raw)
    wire = json.loads(raw)
    assert dto.outcome.status == "RESULT_AVAILABLE"
    assert wire["source"] == {"type": "LOCAL_IMAGE", "provenance": {
        "sourceSystem": LOCAL_IMAGE_SOURCE_SYSTEM,
        "sourceReference": context.source_reference,
        "contentSha256": None,
    }}
    assert wire["automaticExtraction"]["producer"]["producerVersion"] == output.extractor_version
    assert wire["receipt"]["receiptFields"][0]["originalAutomaticValue"] == store
    assert wire["receipt"]["receiptFields"][0]["presentationValue"] == store
    assert wire["receipt"]["itemRows"][0]["fields"][0]["originalAutomaticValue"] == "MILK"
    observed_tokens = wire["sourceEvidence"]["tokenIds"]
    original_tokens = [token.token_id for token in attempt.adapted_source.tokens]
    assert len(observed_tokens) == len(original_tokens)
    assert all(token.encode() not in raw for token in original_tokens)
    expected_store_tokens = [
        observed_tokens[original_tokens.index(token)] for token in output.store_name.source_token_ids
    ]
    assert wire["receipt"]["receiptFields"][0]["sourceTokenIds"] == expected_store_tokens
    assert attempt.b2_result.receipt_output.source_evidence is attempt.source_evidence
    assert attempt.source_evidence.tokens is attempt.adapted_source.tokens


def test_insufficient_retains_evidence_without_receipt_or_extraction(context):
    attempt = _retained(context, decision=SourceEvidenceDecision.INSUFFICIENT)
    result = _decode(context, _emit(context, attempt))
    assert result.outcome.status == "SOURCE_EVIDENCE_INSUFFICIENT"
    assert result.outcome.failure is None
    assert result.source_gate.reasons == (REASON,)
    assert result.source_evidence.token_ids
    assert result.receipt is result.automatic_extraction is None


@pytest.mark.parametrize("case", list(LocalImageFailureV0))
def test_terminal_failure_projects_only_its_retained_stage(context, case):
    attempt = _retained(context)
    if case is LocalImageFailureV0.PROCESSOR_NOT_AVAILABLE:
        attempt = RetainedLocalImageAttemptV0(context.request_id, context.image_id)
    elif case is LocalImageFailureV0.OCR_ENGINE_FAILURE:
        failed_ocr = replace(attempt.adapted_source, processing_status=SourceProcessingStatus.OCR_FAILED)
        attempt = RetainedLocalImageAttemptV0(context.request_id, context.image_id, adapted_source=failed_ocr)
    elif case is LocalImageFailureV0.SOURCE_GATE_EXECUTION_FAILURE:
        attempt = replace(attempt, gate=None, source_evidence=None, b2_result=None)
    elif case is LocalImageFailureV0.EXTRACTION_ENGINE_FAILURE:
        attempt = replace(attempt, b2_result=None)
    dto = _decode(context, _emit(context, replace(attempt, failure=case)))
    stage, code, retryable = case.value
    assert dto.outcome.status == (
        "PROCESSING_UNAVAILABLE" if stage == "AVAILABILITY" else "PROCESSING_FAILED"
    )
    assert (dto.outcome.failure.stage, dto.outcome.failure.code, dto.outcome.failure.retryable) == (
        stage, code, retryable
    )
    assert dto.receipt is dto.automatic_extraction is None
    assert (dto.source_gate is not None) == (stage in {"EXTRACTION", "PRESENTATION_ADAPTER"})


@pytest.mark.parametrize("identity", ["request_id", "image_id"])
def test_terminal_attempt_must_match_independently_retained_ids(context, identity):
    attempt = replace(_retained(context), **{identity: "different-opaque-id"})
    with pytest.raises(LocalImageProjectionError, match="reserved context"):
        _emit(context, attempt)


def test_rejects_source_or_stage_records_from_another_attempt(context):
    attempt = _retained(context)
    other = _retained(context)
    for changes in (
        {"adapted_source": other.adapted_source},
        {"source_evidence": other.source_evidence},
        {"b2_result": other.b2_result},
    ):
        with pytest.raises(LocalImageProjectionError):
            _emit(context, replace(attempt, **changes))


def test_generated_gate_and_fixture_ocr_are_refused(context):
    with pytest.raises(LocalImageProjectionError, match="Android local-image source"):
        _emit(context, _retained(context, source_system="I2B_L05_GENERATED_SYNTHETIC"))
    fixture_policy = LiveGateApprovalV0(
        GATE_C_SOURCE_GATE_V0.policy_id,
        GATE_C_SOURCE_GATE_V0.revision,
        GATE_C_SOURCE_GATE_V0.canonical_sha256.lower(),
        (),
    )
    wrong_context = replace(context, approved_gate=fixture_policy)
    with pytest.raises(LocalImageProjectionError, match="Generated-only Gate C"):
        _emit(wrong_context, _retained(wrong_context))


def test_live_gate_approval_cannot_be_missing_or_substituted(context):
    attempt = _retained(context)
    for policy in (None, replace(context.approved_gate)):
        with pytest.raises(LocalImageProjectionError, match="separately approved LIVE gate"):
            _emit(replace(context, approved_gate=policy), attempt)


def test_gate_reasons_are_neither_free_text_nor_ocr_tokens(context):
    for reason in ("Unapproved reason.", "TEST MART"):
        if reason == "TEST MART":
            context = replace(context, approved_gate=replace(context.approved_gate, public_reasons=(reason,)))
        attempt = _retained(context, decision=SourceEvidenceDecision.INSUFFICIENT, reason=reason)
        with pytest.raises(LocalImageProjectionError, match="approved public literals"):
            _emit(context, attempt)


def test_contradictory_failure_and_post_insufficient_failure_are_refused(context):
    sufficient = _retained(context)
    with pytest.raises(LocalImageProjectionError):
        _emit(context, replace(sufficient, failure=LocalImageFailureV0.OCR_ENGINE_FAILURE))
    insufficient = _retained(context, decision=SourceEvidenceDecision.INSUFFICIENT)
    with pytest.raises(LocalImageProjectionError):
        _emit(context, replace(insufficient, failure=LocalImageFailureV0.PRESENTATION_PROJECTION_FAILURE))


def test_frozen_validator_rejects_unrepresentable_values_without_leaking_detail(context):
    attempt = _retained(context)
    output = attempt.b2_result.receipt_output
    original_date = output.purchase_date
    value = "DO_NOT_DISCLOSE"
    bad_date = replace(original_date, value=value)
    bad_result = replace(attempt.b2_result, receipt_output=replace(output, purchase_date=bad_date))

    with pytest.raises(LocalImageProjectionError) as error:
        _emit(context, replace(attempt, b2_result=bad_result))
    assert value not in str(error.value)
    assert error.value.__context__ is None
