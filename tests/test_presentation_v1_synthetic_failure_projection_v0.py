"""Synthetic acceptance for L03; no inference, transport or operational policy."""

from contextlib import ExitStack
from dataclasses import FrozenInstanceError, asdict, fields, replace
import ast
import hashlib
import inspect
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pipeline import backend_receipt_execution_v0 as l01
from pipeline import baseline_b1, baseline_b3, layout_b2, ocr_adapter
from pipeline.contracts import (
    OutputStage, PolicyState, SourceEvidenceDecision, SourceEvidenceGateResult,
    SourceProcessingStatus,
)
from pipeline.ocr_adapter import adapt_paddleocr_result, attach_gate_result
from pipeline.layout_b2 import extract_b2 as real_extract_b2
from pipeline.presentation_v1 import b2_synthetic_projection_v0 as l02
from pipeline.presentation_v1 import synthetic_failure_projection_v0 as l03
from pipeline.presentation_v1.conformance import ConformanceViolation, decode_and_validate_presentation_v1


C = l03.SyntheticFailureCaseV0
D = l03.SyntheticDeferredEventV0.POST_INSUFFICIENT_PRESENTATION_EXCEPTION
R = l03.NoFailureEnvelopeReasonV0
REQUEST = "request-l03-synthetic"
IMAGE = "image-l03-synthetic"
NAMESPACE = "0123456789abcdef0123456789abcdef"
SAFE = (
    "Synthetic source structure was unavailable.",
    "There is 1 unreadable row.",
    "The x marker was unavailable.",
    "Extraction could not locate 1 safe heading.",
)
EXPECTED = {
    C.PROCESSOR_NOT_AVAILABLE: ("AVAILABILITY", "PROCESSOR_NOT_AVAILABLE", False),
    C.OCR_ENGINE_FAILURE: ("OCR", "OCR_ENGINE_FAILURE", True),
    C.SOURCE_GATE_EXECUTION_FAILURE: ("SOURCE_GATE", "SOURCE_GATE_EXECUTION_FAILURE", True),
    C.EXTRACTION_ENGINE_FAILURE: ("EXTRACTION", "EXTRACTION_ENGINE_FAILURE", True),
    C.PRESENTATION_PROJECTION_FAILURE: ("PRESENTATION_ADAPTER", "PRESENTATION_PROJECTION_FAILURE", True),
}


def context(**changes):
    return replace(l03.SyntheticFailureContextV0(REQUEST, IMAGE, NAMESPACE, "FIXTURE"), **changes)


def graph(status=SourceProcessingStatus.OCR_COMPLETED, decision=SourceEvidenceDecision.SUFFICIENT,
          reasons=SAFE[:1], *, empty=False):
    texts = ["SECRET ORIGINAL STORE", "DATE:", "2026-11-18", "MILK", "1", "x", "5.50", "5.50", "TOTAL", "5.50"]
    boxes = [[20, 0, 200, 10], [10, 20, 55, 30], [70, 20, 170, 30],
             [10, 45, 55, 55], [110, 45, 120, 55], [130, 45, 138, 55],
             [155, 45, 193, 55], [220, 45, 265, 55], [130, 95, 185, 105], [220, 95, 290, 105]]
    source = adapt_paddleocr_result(
        {"rec_texts": [] if empty else texts, "rec_boxes": [] if empty else boxes,
         "rec_scores": [] if empty else [None] * len(texts)},
        receipt_id="private:receipt:l03", image_id=IMAGE,
        source_system="private-source", source_reference="file:///tmp/participant-001.jpg",
        processing_status=status,
    )
    if decision is None:
        return source, None, None
    gate = SourceEvidenceGateResult("private:gate:l03", source.receipt_id, decision, reasons)
    evaluator = Mock(return_value=gate)
    evidence = attach_gate_result(source, evaluator(source))
    evaluator.assert_called_once_with(source)
    assert evidence.tokens is source.tokens and evidence.provenance is source.provenance
    return source, gate, evidence


def facts(case=C.EXTRACTION_ENGINE_FAILURE, *, status=SourceProcessingStatus.OCR_COMPLETED,
          reasons=SAFE[:1], decision=SourceEvidenceDecision.SUFFICIENT, fallback=False, empty=False):
    if status is None:
        source = gate = evidence = None
    else:
        if case in (C.PROCESSOR_NOT_AVAILABLE, C.OCR_ENGINE_FAILURE, C.SOURCE_GATE_EXECUTION_FAILURE):
            decision = None
        if case is D:
            decision = SourceEvidenceDecision.INSUFFICIENT
        source, gate, evidence = graph(status, decision, reasons, empty=empty)
    result = None
    if evidence is not None and (case is C.PRESENTATION_PROJECTION_FAILURE or fallback):
        result = real_extract_b2(evidence)
    return l03.SyntheticFailureFactsV0(REQUEST, IMAGE, case, source, gate, evidence, result)


def emit(failure, ctx=None):
    return l03.build_synthetic_failure_presentation_v1(context=context() if ctx is None else ctx, failure=failure)


def reject(result, reason):
    assert type(result) is l03.NoFailureEnvelopeV0 and result.reason is reason
    assert not hasattr(result, "payload") and not hasattr(result, "__dict__")
    for secret in ("SECRET", "private:", "participant-001", "file:///", "MILK"):
        assert secret not in repr(result)
    assert not hasattr(result, "__cause__") and not hasattr(result, "__context__")
    return result


def decode(result):
    assert type(result) is l03.ValidatedFailureEnvelopeV0 and type(result.payload) is bytes
    return decode_and_validate_presentation_v1(
        result.payload, expected_request_id=REQUEST, expected_image_id=IMAGE, consumer_mode="FIXTURE",
    )


@pytest.mark.parametrize("case", list(C))
@pytest.mark.parametrize("status", [None, *SourceProcessingStatus])
def test_complete_s06_status_matrix(case, status):
    f = facts(case, status=status)
    before = repr(f) + repr((f.adapted_source, f.gate_result, f.source_evidence, f.b2_result))
    allowed = (
        (case is C.PROCESSOR_NOT_AVAILABLE and status is None)
        or (case is C.OCR_ENGINE_FAILURE and status in (None, SourceProcessingStatus.OCR_FAILED))
        or (case in (C.SOURCE_GATE_EXECUTION_FAILURE, C.EXTRACTION_ENGINE_FAILURE,
                     C.PRESENTATION_PROJECTION_FAILURE)
            and status in (SourceProcessingStatus.OCR_COMPLETED, SourceProcessingStatus.OCR_PARTIAL))
    )
    result = emit(f)
    if not allowed:
        reject(result, R.STAGE_NOT_REPRESENTABLE)
    else:
        dto = decode(result)
        wire = json.loads(result.payload)
        stage, code, retry = EXPECTED[case]
        assert (dto.outcome.failure.stage, dto.outcome.failure.code, dto.outcome.failure.retryable) == (stage, code, retry)
        assert type(wire["outcome"]["failure"]["retryable"]) is bool
        assert wire["outcome"]["status"] == ("PROCESSING_UNAVAILABLE" if stage == "AVAILABILITY" else "PROCESSING_FAILED")
        assert wire["automaticExtraction"] is wire["receipt"] is None
        assert set(wire) == {"schemaName", "schemaVersion", "sourceContractVersion", "requestId", "imageId",
                             "source", "outcome", "sourceEvidence", "sourceGate", "automaticExtraction", "receipt"}
        assert wire["source"] == {"type": "SYNTHETIC_FIXTURE", "provenance": {
            "sourceSystem": "I2B_SYNTHETIC_FAILURE_V0", "sourceReference": f"src-v1-{NAMESPACE}-1",
            "contentSha256": None,
        }}
        if f.adapted_source is None:
            assert wire["sourceEvidence"] is wire["sourceGate"] is None
        else:
            assert wire["sourceEvidence"]["sourceProcessingStatus"] == status.value
            assert wire["sourceEvidence"]["tokenIds"] == [
                f"tok-v1-{NAMESPACE}-{i}" for i in range(1, len(f.adapted_source.tokens) + 1)
            ]
            if f.gate_result is None:
                assert wire["sourceGate"] is None
            else:
                assert wire["sourceGate"] == {"gateResultId": f"gat-v1-{NAMESPACE}-1",
                                               "decision": "SUFFICIENT", "reasons": list(f.gate_result.reasons)}
        for private in ("SECRET", "private:", "participant-001", "file:///", "MILK", "polygon", "original_text"):
            assert private not in result.payload.decode()
    assert before == repr(f) + repr((f.adapted_source, f.gate_result, f.source_evidence, f.b2_result))


@pytest.mark.parametrize("case", [C.OCR_ENGINE_FAILURE, C.SOURCE_GATE_EXECUTION_FAILURE])
@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
def test_durable_gate_forbids_ocr_and_gate_failure(case, decision):
    source, gate, evidence = graph(SourceProcessingStatus.OCR_FAILED if case is C.OCR_ENGINE_FAILURE
                                    else SourceProcessingStatus.OCR_COMPLETED, decision)
    f = l03.SyntheticFailureFactsV0(REQUEST, IMAGE, case, source, gate, evidence, None)
    reject(emit(f), R.STAGE_NOT_REPRESENTABLE)
    # A returned but not yet attached gate must not be silently discarded.
    reject(emit(replace(f, source_evidence=None)), R.STAGE_NOT_REPRESENTABLE)


@pytest.mark.parametrize("case", [C.EXTRACTION_ENGINE_FAILURE, C.PRESENTATION_PROJECTION_FAILURE])
def test_missing_sufficient_gate_or_original_output_is_not_reconstructed(case):
    f = facts(case)
    reject(emit(replace(f, gate_result=None, source_evidence=None, b2_result=None)), R.STAGE_NOT_REPRESENTABLE)
    if case is C.PRESENTATION_PROJECTION_FAILURE:
        reject(emit(replace(f, b2_result=None)), R.STAGE_NOT_REPRESENTABLE)
    else:
        reject(emit(replace(f, b2_result=real_extract_b2(f.source_evidence))), R.STAGE_NOT_REPRESENTABLE)


def test_empty_tokens_do_not_create_a_new_minimum_or_reclassify_structural_failed():
    f = facts(C.PRESENTATION_PROJECTION_FAILURE, empty=True)
    assert f.b2_result.receipt_output.extraction_status.value == "FAILED"
    dto = decode(emit(f))
    assert dto.source_evidence.token_ids == ()
    # The supplied case reports a separate projection exception. Without that
    # event the real structural FAILED result remains L02's available outcome.
    reject(emit(f.b2_result), R.INVALID_INPUT)
    with patch.object(layout_b2, "extract_b2", wraps=real_extract_b2), \
         patch.object(l02, "extract_b2", wraps=real_extract_b2) as b2:
        raw = l02.extract_b2_fixture_presentation_v1(
            adapted_source=f.adapted_source, source_evidence=f.source_evidence,
            request_id=REQUEST, image_id=IMAGE, alias_namespace=NAMESPACE,
            producer_id="synthetic-l03-test", consumer_mode="FIXTURE",
        )
    b2.assert_called_once_with(f.source_evidence)
    assert json.loads(raw)["outcome"]["status"] == "RESULT_AVAILABLE"
    assert json.loads(raw)["automaticExtraction"]["extractionStatus"] == "FAILED"


@pytest.mark.parametrize("status", list(SourceProcessingStatus))
@pytest.mark.parametrize("with_fallback", [False, True])
def test_exact_deferred_event_all_genuine_statuses_and_optional_fallback(status, with_fallback):
    f = facts(D, status=status, fallback=with_fallback, reasons=("file:///tmp/participant-001.jpg",))
    before = repr((f.adapted_source, f.gate_result, f.source_evidence, f.b2_result))
    with patch.object(l03, "_stage_representable", side_effect=AssertionError("late stage check")), \
         patch.object(l03, "_envelope", side_effect=AssertionError("must not emit")), \
         patch.object(l03, "decode_and_validate_presentation_v1", side_effect=AssertionError("no validator")), \
         patch.object(l03, "_gate_reasons_safe", side_effect=AssertionError("no reason check")):
        reject(emit(f), R.DEFERRED_POST_INSUFFICIENT)
    assert before == repr((f.adapted_source, f.gate_result, f.source_evidence, f.b2_result))


@pytest.mark.parametrize("fault,expected", [
    ("missing_gate", R.INVALID_ASSOCIATION), ("missing_source", R.INVALID_ASSOCIATION),
    ("missing_witness_chain", R.STAGE_NOT_REPRESENTABLE),
    ("gate_copy", R.INVALID_ASSOCIATION), ("source_copy_tokens", R.INVALID_ASSOCIATION),
    ("evidence_copy_provenance", R.INVALID_ASSOCIATION), ("receipt", R.INVALID_ASSOCIATION),
    ("fallback_gate", R.INVALID_ASSOCIATION), ("sufficient_only", R.INVALID_ASSOCIATION),
    ("coherent_sufficient", R.STAGE_NOT_REPRESENTABLE), ("ordinary_case", R.STAGE_NOT_REPRESENTABLE),
    ("raw_discriminator", R.INVALID_INPUT), ("wrong_request", R.CORRELATION_MISMATCH),
    ("wrong_image", R.CORRELATION_MISMATCH),
])
def test_deferred_rejection_distinctions(fault, expected):
    f = facts(D, fallback=True)
    if fault == "missing_gate":
        f = replace(f, gate_result=None)
    elif fault == "missing_source":
        f = replace(f, adapted_source=None)
    elif fault == "missing_witness_chain":
        f = replace(f, gate_result=None, source_evidence=None, b2_result=None)
    elif fault == "gate_copy":
        f = replace(f, gate_result=replace(f.gate_result))
    elif fault == "source_copy_tokens":
        f = replace(f, adapted_source=replace(f.adapted_source, tokens=tuple(list(f.adapted_source.tokens))))
    elif fault == "evidence_copy_provenance":
        f = replace(f, source_evidence=replace(f.source_evidence, provenance=replace(f.source_evidence.provenance)))
    elif fault == "receipt":
        object.__setattr__(f.gate_result, "receipt_id", "foreign-receipt")
    elif fault == "fallback_gate":
        object.__setattr__(f.b2_result.pre_resolution_disposition, "gate_result", replace(f.gate_result))
    elif fault == "sufficient_only":
        f = replace(f, gate_result=replace(f.gate_result, decision=SourceEvidenceDecision.SUFFICIENT))
    elif fault == "coherent_sufficient":
        source, gate, evidence = graph()
        f = replace(f, adapted_source=source, gate_result=gate, source_evidence=evidence, b2_result=real_extract_b2(evidence))
    elif fault == "ordinary_case":
        f = replace(f, case=C.PRESENTATION_PROJECTION_FAILURE)
    elif fault == "raw_discriminator":
        f = replace(f, case=D.value)
    elif fault == "wrong_request":
        f = replace(f, request_id="other-request")
    else:
        f = replace(f, image_id="other-image")
    reject(emit(f), expected)


@pytest.mark.parametrize("fault", [
    "evidence_copy", "source_provenance", "source_tokens", "gate_owner", "token_owner",
    "duplicate_token", "duplicate_field", "unknown_token", "row_owner", "output_stage",
    "missing_evidence", "processing_status", "bad_geometry", "bad_confidence",
    "both_result_branches", "neither_result_branch", "contradictory_fallback",
])
def test_invalid_original_associations_are_rejected(fault):
    f = facts(C.PRESENTATION_PROJECTION_FAILURE)
    if fault == "evidence_copy":
        f = replace(f, source_evidence=replace(f.source_evidence))
    elif fault == "source_provenance":
        f = replace(f, adapted_source=replace(f.adapted_source, provenance=replace(f.adapted_source.provenance)))
    elif fault == "source_tokens":
        f = replace(f, source_evidence=replace(f.source_evidence, tokens=tuple(list(f.source_evidence.tokens))))
    elif fault == "gate_owner":
        object.__setattr__(f.gate_result, "receipt_id", "foreign")
    elif fault == "token_owner":
        object.__setattr__(f.adapted_source.tokens[0], "receipt_id", "foreign")
    elif fault == "duplicate_token":
        duplicate = (f.adapted_source.tokens[0], f.adapted_source.tokens[0])
        object.__setattr__(f.adapted_source, "tokens", duplicate)
        object.__setattr__(f.source_evidence, "tokens", duplicate)
    elif fault == "duplicate_field":
        output = f.b2_result.receipt_output
        object.__setattr__(output.purchase_date, "field_id", output.store_name.field_id)
    elif fault == "unknown_token":
        object.__setattr__(f.b2_result.receipt_output.store_name, "source_token_ids", ("private:unknown",))
    elif fault == "row_owner":
        object.__setattr__(f.b2_result.receipt_output.items[0].quantity, "item_row_id", "foreign")
    elif fault == "output_stage":
        object.__setattr__(f.b2_result.receipt_output, "output_stage", OutputStage.HUMAN_REVIEWED)
    elif fault == "missing_evidence":
        f = replace(f, source_evidence=None)
    elif fault == "processing_status":
        f = replace(f, source_evidence=replace(f.source_evidence, processing_status=SourceProcessingStatus.OCR_PARTIAL))
    elif fault == "bad_geometry":
        object.__setattr__(f.adapted_source.tokens[0].polygon[0], "x", float("inf"))
    elif fault == "bad_confidence":
        object.__setattr__(f.b2_result.receipt_output.store_name, "confidence", float("nan"))
    elif fault == "both_result_branches":
        fallback = facts(D, fallback=True).b2_result.pre_resolution_disposition
        object.__setattr__(f.b2_result, "pre_resolution_disposition", fallback)
    elif fault == "neither_result_branch":
        object.__setattr__(f.b2_result, "receipt_output", None)
    else:
        f = facts(D, fallback=True)
        object.__setattr__(f.b2_result.pre_resolution_disposition, "state", PolicyState.FAILED)
    reject(emit(f), R.INVALID_ASSOCIATION)


class Hostile:
    def __getattribute__(self, name):
        raise AssertionError("untrusted attribute access")

    def __eq__(self, other):
        raise AssertionError("untrusted equality")

    def __hash__(self):
        raise AssertionError("untrusted hash")

    def __iter__(self):
        raise AssertionError("untrusted iteration")

    def __str__(self):
        raise AssertionError("untrusted str")

    def __repr__(self):
        raise AssertionError("untrusted repr")


class HostileString(str):
    __eq__ = Hostile.__eq__
    __hash__ = Hostile.__hash__
    __str__ = Hostile.__str__
    __repr__ = Hostile.__repr__


class HostileTuple(tuple):
    __iter__ = Hostile.__iter__


@pytest.mark.parametrize("fault", [
    "outer_context", "outer_facts", "missing_slot", "request", "namespace", "mode", "case",
    "source", "gate", "evidence", "b2", "text", "tuple", "point", "confidence", "status",
    "source_subclass", "context_subclass", "forged_enum",
])
def test_hostile_shapes_reject_without_dynamic_operations(fault):
    f, ctx = facts(), context()
    if fault == "outer_context":
        ctx = Hostile()
    elif fault == "outer_facts":
        f = Hostile()
    elif fault == "missing_slot":
        ctx = object.__new__(l03.SyntheticFailureContextV0)
    elif fault == "request":
        ctx = replace(ctx, request_id=HostileString(REQUEST))
    elif fault == "namespace":
        ctx = replace(ctx, alias_namespace=Hostile())
    elif fault == "mode":
        ctx = replace(ctx, consumer_mode=Hostile())
    elif fault == "case":
        f = replace(f, case=Hostile())
    elif fault in ("source", "gate", "evidence", "b2"):
        name = {"source": "adapted_source", "gate": "gate_result", "evidence": "source_evidence", "b2": "b2_result"}[fault]
        f = replace(f, **{name: Hostile()})
    elif fault == "text":
        object.__setattr__(f.adapted_source.tokens[0], "original_text", Hostile())
    elif fault == "tuple":
        object.__setattr__(f.adapted_source, "tokens", HostileTuple(f.adapted_source.tokens))
    elif fault == "point":
        object.__setattr__(f.adapted_source.tokens[0].polygon[0], "x", Hostile())
    elif fault == "confidence":
        object.__setattr__(f.adapted_source.tokens[0], "raw_confidence", True)
    elif fault == "status":
        object.__setattr__(f.adapted_source, "processing_status", "OCR_COMPLETED")
    elif fault == "source_subclass":
        class ForeignSource(ocr_adapter.AdaptedOcrSource):
            __getattribute__ = Hostile.__getattribute__
        f = replace(f, adapted_source=object.__new__(ForeignSource))
    elif fault == "context_subclass":
        class ForeignContext(l03.SyntheticFailureContextV0):
            __getattribute__ = Hostile.__getattribute__
        ctx = object.__new__(ForeignContext)
    else:
        forged = str.__new__(SourceEvidenceDecision, "SUFFICIENT")
        object.__setattr__(f.gate_result, "decision", forged)
    reject(emit(f, ctx), R.INVALID_INPUT)


@pytest.mark.parametrize("changes", [
    {"consumer_mode": "LIVE"}, {"consumer_mode": "fixture"},
    {"request_id": "file:///tmp/participant-001.jpg"}, {"image_id": "participant-001"},
    {"request_id": ""}, {"request_id": "request\n"}, {"alias_namespace": "a" * 31},
    {"alias_namespace": "A" * 32}, {"alias_namespace": "g" * 32}, {"alias_namespace": "a" * 32 + "\n"},
])
def test_invalid_context_values(changes):
    reject(emit(facts(), context(**changes)), R.INVALID_INPUT)


@pytest.mark.parametrize("priority", [1, 2, 3, 4, 5])
def test_earlier_deterministic_rejection_prevents_every_later_fault(priority):
    f, ctx = facts(D), context()
    phases = ["_inputs_valid", "_correlated", "_associations_valid", "_valid_deferred_event", "_stage_representable"]
    if priority == 1:
        ctx = replace(ctx, consumer_mode="LIVE", request_id="wrong-request")
        object.__setattr__(f.gate_result, "receipt_id", "foreign")
    elif priority == 2:
        ctx = replace(ctx, request_id="wrong-request")
        object.__setattr__(f.gate_result, "receipt_id", "foreign")
    elif priority == 3:
        f = replace(f, gate_result=replace(f.gate_result))
    elif priority == 5:
        f = replace(f, case=C.PRESENTATION_PROJECTION_FAILURE)
    later = phases[priority:] + ["_envelope", "_serialize", "decode_and_validate_presentation_v1", "_gate_reasons_safe"]
    with ExitStack() as stack:
        spies = [stack.enter_context(patch.object(l03, name, side_effect=RuntimeError("SECRET late fault"))) for name in later]
        result = emit(f, ctx)
    reject(result, list(R)[priority - 1])
    assert all(spy.call_count == 0 for spy in spies)


def test_v1_rejection_precedes_source_aware_reason_rejection():
    f = facts(reasons=("Unapproved generic explanation.",))
    real_envelope = l03._envelope
    observed = []

    def invalid_envelope(*args):
        value = real_envelope(*args)
        value["schemaVersion"] = "999"
        return value

    def validate(raw, **kwargs):
        try:
            return decode_and_validate_presentation_v1(raw, **kwargs)
        except ConformanceViolation as error:
            observed.append(error.code)
            raise

    with patch.object(l03, "_envelope", side_effect=invalid_envelope), \
         patch.object(l03, "decode_and_validate_presentation_v1", side_effect=validate), \
         patch.object(l03, "_gate_reasons_safe", side_effect=RuntimeError("SECRET late")) as late:
        reject(emit(f), R.V1_VALIDATION_REJECTED)
    assert observed == ["REJECT_UNSUPPORTED_SCHEMA_VERSION"] and late.call_count == 0


@pytest.mark.parametrize("reason", ["", " \t\r\n", "file:///tmp/participant-001.jpg", "OCR:failed"])
def test_existing_v1_reason_checks_precede_vocabulary(reason):
    f = facts(reasons=(reason,))
    with patch.object(l03, "_gate_reasons_safe", side_effect=AssertionError("late")) as late:
        reject(emit(f), R.V1_VALIDATION_REJECTED)
    late.assert_not_called()


@pytest.mark.parametrize("reason", ["MILK", "1", "x", "Unable to read MILK during capture.",
                                    "Unapproved generic explanation.", "\u00a0"])
def test_source_aware_admission_after_successful_v1_validation(reason):
    f = facts(reasons=(reason,))
    with patch.object(l03, "decode_and_validate_presentation_v1", wraps=decode_and_validate_presentation_v1) as validator:
        reject(emit(f), R.UNSAFE_GATE_REASON)
    validator.assert_called_once()


@pytest.mark.parametrize("reason", SAFE)
def test_approved_prose_short_token_collisions_and_exact_transcription_veto(reason):
    f = facts(reasons=(reason,))
    assert {"1", "x"} <= {token.original_text for token in f.adapted_source.tokens}
    assert decode(emit(f)).source_gate.reasons == (reason,)
    replacement = replace(f.adapted_source.tokens[0], original_text=reason)
    tokens = (replacement,) + f.adapted_source.tokens[1:]
    source = replace(f.adapted_source, tokens=tokens)
    evidence = replace(f.source_evidence, tokens=tokens)
    f = replace(f, adapted_source=source, source_evidence=evidence)
    reject(emit(f), R.UNSAFE_GATE_REASON)


def test_multiple_reasons_order_and_original_evidence_are_preserved():
    f = facts(reasons=SAFE)
    before = asdict(f)
    assert decode(emit(f)).source_gate.reasons == SAFE
    assert before == asdict(f)


def test_duplicate_recorded_reasons_fail_association_before_emission():
    f = facts()
    object.__setattr__(f.gate_result, "reasons", (SAFE[0], SAFE[0]))
    with patch.object(l03, "_envelope", side_effect=AssertionError("late")) as later:
        reject(emit(f), R.INVALID_ASSOCIATION)
    later.assert_not_called()


def test_empty_sufficient_reasons_remain_allowed():
    f = facts(reasons=())
    assert decode(emit(f)).source_gate.reasons == ()


@pytest.mark.parametrize("confidence", [None, 0.0, -0.0, 0.875, 1.0])
def test_native_source_confidence_is_preserved_without_wire_disclosure(confidence):
    f = facts()
    tokens = tuple(replace(token, raw_confidence=confidence) for token in f.adapted_source.tokens)
    source = replace(f.adapted_source, tokens=tokens)
    evidence = replace(f.source_evidence, tokens=tokens)
    f = replace(f, adapted_source=source, source_evidence=evidence)
    before = asdict(f)
    result = emit(f)
    decode(result)
    assert before == asdict(f)
    assert all(token.raw_confidence is confidence for token in tokens)
    assert evidence.tokens is source.tokens is tokens
    assert b"confidence" not in result.payload.lower()


@pytest.mark.parametrize("phase", ["_associations_valid", "_envelope", "_serialize", "_gate_reasons_safe"])
def test_unexpected_exception_before_rejection_is_emission_failed(phase):
    with patch.object(l03, phase, side_effect=RuntimeError("SECRET file:///tmp/participant-001.jpg")):
        reject(emit(facts()), R.EMISSION_FAILED)


def test_expected_record_validation_failure_is_association_not_emission_error():
    f = facts()
    with patch.object(type(f.gate_result), "__post_init__", side_effect=ValueError("SECRET")):
        reject(emit(f), R.INVALID_ASSOCIATION)


@pytest.mark.parametrize("error_type,expected", [(ConformanceViolation, R.V1_VALIDATION_REJECTED), (RuntimeError, R.EMISSION_FAILED)])
def test_hostile_exception_metadata_chains_and_notes_are_not_retained(error_type, expected, capsys):
    try:
        raise ValueError("SECRET cause file:///tmp/participant-001.jpg")
    except ValueError as cause:
        try:
            if error_type is ConformanceViolation:
                raise ConformanceViolation("SECRET code", "$.private:receipt", "SECRET detail") from cause
            raise RuntimeError("SECRET upstream") from cause
        except Exception as original:
            error = original
    error.add_note("SECRET note")
    if error_type is ConformanceViolation:
        error.code = Hostile()
        error.path = Hostile()
        error.detail = Hostile()
    with patch.object(l03, "decode_and_validate_presentation_v1", side_effect=error):
        result = reject(emit(facts()), expected)
    assert [field.name for field in fields(result)] == ["reason"]
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit])
def test_base_exception_is_not_reinterpreted_as_processing_failure(signal):
    with patch.object(l03, "_serialize", side_effect=signal):
        with pytest.raises(signal):
            emit(facts())


def test_determinism_strict_bytes_and_independent_consumer_context_rejection():
    f = facts(C.PRESENTATION_PROJECTION_FAILURE)
    with patch.object(l03, "decode_and_validate_presentation_v1", wraps=decode_and_validate_presentation_v1) as validator:
        first, second = emit(f), emit(f)
    assert first.payload == second.payload
    assert validator.call_args.args[0] is second.payload
    assert second.payload == json.dumps(json.loads(second.payload), sort_keys=True, ensure_ascii=True,
                                       allow_nan=False, separators=(",", ":")).encode("utf-8")
    assert not second.payload.startswith(b"\xef\xbb\xbf") and second.payload.endswith(b"}")
    for request, image, expected in [("other-request", IMAGE, "REJECT_REQUEST_ID_MISMATCH"),
                                     (REQUEST, "other-image", "REJECT_IMAGE_ID_MISMATCH")]:
        with pytest.raises(ConformanceViolation) as caught:
            decode_and_validate_presentation_v1(second.payload, expected_request_id=request,
                                                expected_image_id=image, consumer_mode="FIXTURE")
        assert caught.value.code == expected


def test_no_upstream_execution_or_external_side_effects(capsys):
    prepared = [facts(C.PROCESSOR_NOT_AVAILABLE, status=None), facts(C.OCR_ENGINE_FAILURE, status=None),
                facts(C.SOURCE_GATE_EXECUTION_FAILURE), facts(), facts(C.PRESENTATION_PROJECTION_FAILURE), facts(D)]
    before = [asdict(f) for f in prepared]
    targets = [(ocr_adapter, "adapt_paddleocr_result"), (ocr_adapter, "attach_gate_result"),
               (layout_b2, "extract_b2"), (baseline_b1, "extract_b1"), (baseline_b3, "apply_b3"),
               (l01, "extract_adapted_receipt_v0"), (l02, "extract_b2_fixture_presentation_v1")]
    with ExitStack() as stack:
        spies = [stack.enter_context(patch.object(module, name, side_effect=AssertionError("upstream execution")))
                 for module, name in targets]
        for target in ("builtins.open", "pathlib.Path.open", "os.open", "socket.socket", "subprocess.Popen"):
            stack.enter_context(patch(target, side_effect=AssertionError("external side effect")))
        results = [emit(f) for f in prepared]
    assert all(type(result) is l03.ValidatedFailureEnvelopeV0 for result in results[:-1])
    reject(results[-1], R.DEFERRED_POST_INSUFFICIENT)
    assert all(spy.call_count == 0 for spy in spies)
    assert before == [asdict(f) for f in prepared]
    assert capsys.readouterr() == ("", "")


def test_public_api_record_shapes_immutability_enum_counts_and_import_boundary():
    assert len(C) == 5 and len(l03.SyntheticDeferredEventV0) == 1 and len(R) == 8
    assert [item.name for item in R] == ["INVALID_INPUT", "CORRELATION_MISMATCH", "INVALID_ASSOCIATION",
        "DEFERRED_POST_INSUFFICIENT", "STAGE_NOT_REPRESENTABLE", "V1_VALIDATION_REJECTED", "UNSAFE_GATE_REASON", "EMISSION_FAILED"]
    signature = inspect.signature(l03.build_synthetic_failure_presentation_v1)
    assert list(signature.parameters) == ["context", "failure"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is inspect.Parameter.empty
               for p in signature.parameters.values())
    expected = {
        l03.SyntheticFailureContextV0: ["request_id", "image_id", "alias_namespace", "consumer_mode"],
        l03.SyntheticFailureFactsV0: ["request_id", "image_id", "case", "adapted_source", "gate_result", "source_evidence", "b2_result"],
        l03.ValidatedFailureEnvelopeV0: ["payload"], l03.NoFailureEnvelopeV0: ["reason"],
    }
    for record_type, names in expected.items():
        assert [field.name for field in fields(record_type)] == names
        assert record_type.__dataclass_params__.frozen and record_type.__dataclass_params__.repr is False
        assert list(record_type.__slots__) == names
        assert all(field.default is __import__("dataclasses").MISSING for field in fields(record_type))
    ctx = context()
    with pytest.raises(FrozenInstanceError):
        ctx.request_id = "changed"
    tree = ast.parse(inspect.getsource(l03))
    modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(module.startswith(("tests", "pipeline.proposed", "pipeline.backend_receipt_execution")) for module in modules)
    assert "pipeline.presentation_v1.b2_synthetic_projection_v0" not in modules


def test_canonical_fixtures_remain_exact():
    root = Path(__file__).resolve().parent / "fixtures/receipt_presentation_v1/v1"
    raw = (root / "manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "4b1bcd3445d82852c7f4c3beb5f0e07f39853497e92713b81a063dcdf5350ee9"
    entries = json.loads(raw)["fixtures"]
    assert len(entries) == len({entry["path"] for entry in entries}) == 32
    assert sum(entry["expectedResult"] == "ACCEPT" for entry in entries) == 17
    assert sum(entry["expectedResult"].startswith("REJECT_" ) for entry in entries) == 15
    for entry in entries:
        payload = (root / entry["path"]).read_bytes()
        assert len(payload) == entry["byteLength"]
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
