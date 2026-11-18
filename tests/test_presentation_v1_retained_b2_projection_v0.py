"""Synthetic retained-result acceptance; no operational execution or policy."""

from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
from types import ModuleType
from unittest.mock import Mock, patch

import pytest

from pipeline import backend_receipt_execution_v0 as l01
from pipeline import baseline_b1, baseline_b3, layout_b2, ocr_adapter
from pipeline.contracts import (
    OutputStage, PolicyState, ReceiptExtractionStatus, SourceEvidenceDecision,
    SourceEvidenceGateResult, SourceProcessingStatus,
)
from pipeline.presentation_v1 import b2_synthetic_projection_v0 as projection
from pipeline.presentation_v1 import synthetic_failure_projection_v0 as l03
from pipeline.presentation_v1.conformance import ConformanceViolation, decode_and_validate_presentation_v1
from tests import test_presentation_v1_b2_synthetic_projection_v0 as existing


def retained(source, evidence, result, **changes):
    arguments = dict(
        adapted_source=source, source_evidence=evidence, b2_result=result,
        request_id=existing.REQUEST, image_id=existing.IMAGE,
        alias_namespace=existing.NAMESPACE, producer_id=existing.PRODUCER, consumer_mode="FIXTURE",
    )
    arguments.update(changes)
    return projection.project_retained_b2_fixture_presentation_v1(**arguments)


@contextmanager
def no_upstream():
    targets = [
        (projection, "extract_b2"), (layout_b2, "extract_b2"),
        (ocr_adapter, "adapt_paddleocr_result"), (ocr_adapter, "attach_gate_result"),
        (baseline_b1, "extract_b1"), (baseline_b3, "apply_b3"),
        (l01, "extract_adapted_receipt_v0"), (l03, "build_synthetic_failure_presentation_v1"),
    ]
    with ExitStack() as stack:
        spies = [stack.enter_context(patch.object(module, name, side_effect=AssertionError("Unexpected upstream call.")))
                 for module, name in targets]
        yield
    assert all(spy.call_count == 0 for spy in spies)


@pytest.fixture(scope="module")
def accepted_l02():
    """Independent pre-change byte/exception oracle, read from its pinned Git blob.

    This is read-only Git access. It creates no alternate source file, fixture
    or checkout and does not use the modified shared projection implementation.
    """
    root = Path(__file__).resolve().parents[1]
    raw = subprocess.check_output([
        "git", "--no-optional-locks", "show",
        "b7fb5369d3ed9f4823a9c391f2059befec5183d1:pipeline/presentation_v1/b2_synthetic_projection_v0.py",
    ], cwd=root)
    assert hashlib.sha256(raw).hexdigest() == "0c6e97abf3fb567c455493400c55d75b82ff5bfe23c23ab4d0cc154359a34c97"
    module = ModuleType("accepted_l02_before_retained_seam")
    exec(compile(raw, "<accepted-l02-git-blob>", "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("status", list(SourceProcessingStatus))
@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("options", [{}, {"empty": True}, {"partial": True},
                                    {"no_store": True}, {"reverse_rows": True}])
def test_retained_outcomes_and_exact_bytes_against_both_extracting_versions(status, decision, options, accepted_l02):
    source, evidence, evaluator = existing.prepare(status=status, decision=decision, **options)
    # These are deliberately separate baseline/setup invocations, not one
    # integrated execution. Each extracting producer runs B2 independently.
    context = dict(adapted_source=source, source_evidence=evidence, request_id=existing.REQUEST,
                   image_id=existing.IMAGE, alias_namespace=existing.NAMESPACE,
                   producer_id=existing.PRODUCER, consumer_mode="FIXTURE")
    original = accepted_l02.extract_b2_fixture_presentation_v1(**context)
    with patch.object(projection, "extract_b2", wraps=layout_b2.extract_b2) as extracting:
        current = projection.extract_b2_fixture_presentation_v1(**context)
    extracting.assert_called_once_with(evidence)
    result = layout_b2.extract_b2(evidence)
    before = asdict(source), asdict(evidence), asdict(result)
    with no_upstream():
        raw = retained(source, evidence, result)
        again = retained(source, evidence, result)
    assert raw == again == current == original
    dto = existing.validated(raw)
    wire = json.loads(raw)
    assert dto.source_evidence.source_processing_status == status.value
    assert dto.source_gate.decision == decision.value
    assert dto.source_gate.reasons == evidence.gate_result.reasons
    assert wire["outcome"]["failure"] is None
    assert wire["source"]["provenance"] == {
        "sourceSystem": "I2B_SYNTHETIC_B2_V0", "sourceReference": f"src-v1-{existing.NAMESPACE}-1",
        "contentSha256": None,
    }
    assert wire["sourceEvidence"]["tokenIds"] == [f"tok-v1-{existing.NAMESPACE}-{n}"
                                                   for n in range(1, len(source.tokens) + 1)]
    if decision is SourceEvidenceDecision.INSUFFICIENT:
        assert dto.outcome.status == "SOURCE_EVIDENCE_INSUFFICIENT"
        assert wire["automaticExtraction"] is wire["receipt"] is None
        assert result.pre_resolution_disposition.gate_result is evidence.gate_result
    else:
        assert dto.outcome.status == "RESULT_AVAILABLE"
        assert dto.automatic_extraction.extraction_status == result.receipt_output.extraction_status.value
        assert wire["automaticExtraction"]["producer"]["producerVersion"] == result.receipt_output.extractor_version
        assert wire["receipt"]["receiptId"] == f"rct-v1-{existing.NAMESPACE}-1"
        assert result.receipt_output.source_evidence is evidence
        if options.get("empty"):
            assert result.receipt_output.extraction_status is ReceiptExtractionStatus.FAILED
    assert before == (asdict(source), asdict(evidence), asdict(result))
    evaluator.assert_called_once_with(source)


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
def test_single_integrated_gate_attachment_and_b2_then_zero_additional_execution(decision):
    # No preparation helper runs a gate or attachment for this invocation.
    source = ocr_adapter.adapt_paddleocr_result(
        {"rec_texts": ["SYNTHETIC MART", "DATE: 2026-11-18", "TOTAL 11.00"],
         "rec_boxes": [[0, 0, 150, 10], [0, 20, 150, 30], [0, 80, 150, 90]],
         "rec_scores": [None, -0.0, 0.75]},
        receipt_id="private:integrated-receipt", image_id=existing.IMAGE,
        source_system="private-source", source_reference="file:///tmp/private-source.jpg",
        processing_status=SourceProcessingStatus.OCR_COMPLETED,
    )
    gate = SourceEvidenceGateResult("private:integrated-gate", source.receipt_id,
                                    decision, existing.APPROVED_REASONS[:1])
    events = []
    evaluator = Mock(side_effect=lambda actual: (events.append("gate"), gate)[1])
    actual_attach, actual_b2 = ocr_adapter.attach_gate_result, layout_b2.extract_b2

    def attach(actual_source, actual_gate):
        events.append("attach")
        return actual_attach(actual_source, actual_gate)

    def extract(actual_evidence):
        events.append("b2")
        return actual_b2(actual_evidence)

    with patch.object(ocr_adapter, "attach_gate_result", side_effect=attach) as attachment, \
         patch.object(layout_b2, "extract_b2", side_effect=extract) as b2, \
         patch.object(projection, "extract_b2", side_effect=AssertionError("Second B2.")) as second:
        returned_gate = evaluator(source)
        evidence = ocr_adapter.attach_gate_result(source, returned_gate)
        result = layout_b2.extract_b2(evidence)
        before = asdict(source), asdict(evidence), asdict(result)
        events.append("project")
        raw = retained(source, evidence, result)
    assert events == ["gate", "attach", "b2", "project"]
    evaluator.assert_called_once_with(source)
    attachment.assert_called_once_with(source, gate)
    b2.assert_called_once_with(evidence)
    second.assert_not_called()
    assert evidence.tokens is source.tokens and evidence.provenance is source.provenance
    assert evidence.gate_result is gate
    if decision is SourceEvidenceDecision.SUFFICIENT:
        assert result.receipt_output.source_evidence is evidence
    else:
        assert result.pre_resolution_disposition.gate_result is gate
    existing.validated(raw)
    assert before == (asdict(source), asdict(evidence), asdict(result))


@pytest.mark.parametrize("fault", [
    "foreign_source", "evidence_copy", "tokens_copy", "provenance_copy", "source_receipt",
    "gate_owner", "status_mismatch", "status_string", "decision_string", "duplicate_token",
    "token_owner", "geometry", "output_owner", "duplicate_field", "unknown_token", "row_owner",
    "wrong_stage", "invalid_extraction_enum", "invalid_confidence", "both_branches", "neither_branch",
    "missing_evidence", "missing_result", "unsupported_result",
])
def test_original_record_substitution_and_contradictions_fail_without_execution(fault):
    source, evidence, _ = existing.prepare()
    result = layout_b2.extract_b2(evidence)
    if fault == "foreign_source":
        source = existing.prepare()[0]
    elif fault == "evidence_copy":
        evidence = replace(evidence)
    elif fault == "tokens_copy":
        evidence = replace(evidence, tokens=tuple(list(source.tokens)))
    elif fault == "provenance_copy":
        evidence = replace(evidence, provenance=replace(source.provenance))
    elif fault == "source_receipt":
        object.__setattr__(source, "receipt_id", "foreign-receipt")
    elif fault == "gate_owner":
        object.__setattr__(evidence.gate_result, "receipt_id", "foreign-receipt")
    elif fault == "status_mismatch":
        object.__setattr__(evidence, "processing_status", SourceProcessingStatus.OCR_PARTIAL)
    elif fault == "status_string":
        object.__setattr__(source, "processing_status", "OCR_COMPLETED")
    elif fault == "decision_string":
        object.__setattr__(evidence.gate_result, "decision", "SUFFICIENT")
    elif fault == "duplicate_token":
        tokens = (source.tokens[0], source.tokens[0])
        object.__setattr__(source, "tokens", tokens)
        object.__setattr__(evidence, "tokens", tokens)
    elif fault == "token_owner":
        object.__setattr__(source.tokens[0], "receipt_id", "foreign-receipt")
    elif fault == "geometry":
        object.__setattr__(source.tokens[0].polygon[0], "x", float("nan"))
    elif fault == "output_owner":
        object.__setattr__(result.receipt_output, "receipt_id", "foreign-receipt")
    elif fault == "duplicate_field":
        object.__setattr__(result.receipt_output.purchase_date, "field_id", result.receipt_output.store_name.field_id)
    elif fault == "unknown_token":
        object.__setattr__(result.receipt_output.store_name, "source_token_ids", ("private:unknown",))
    elif fault == "row_owner":
        object.__setattr__(result.receipt_output.items[0].quantity, "item_row_id", "foreign-row")
    elif fault == "wrong_stage":
        object.__setattr__(result.receipt_output, "output_stage", OutputStage.HUMAN_REVIEWED)
    elif fault == "invalid_extraction_enum":
        object.__setattr__(result.receipt_output, "extraction_status", "FAILED")
    elif fault == "invalid_confidence":
        object.__setattr__(result.receipt_output.store_name, "confidence", True)
    elif fault == "both_branches":
        _, other_evidence, _ = existing.prepare(decision=SourceEvidenceDecision.INSUFFICIENT)
        object.__setattr__(result, "pre_resolution_disposition", layout_b2.extract_b2(other_evidence).pre_resolution_disposition)
    elif fault == "neither_branch":
        object.__setattr__(result, "receipt_output", None)
    elif fault == "missing_evidence":
        evidence = None
    elif fault == "missing_result":
        result = None
    else:
        result = {"receipt_output": "private:fake"}
    with no_upstream(), pytest.raises(ValueError) as caught:
        retained(source, evidence, result)
    assert type(caught.value) is ValueError
    assert caught.value.args == ("Invalid synthetic B2-to-V1 input or result.",)
    existing.assert_safe_failure(caught.value)


@pytest.mark.parametrize("fault", ["gate_copy", "wrong_state", "sufficient_gate", "missing_fallback"])
def test_invalid_original_insufficient_fallback_is_not_replaced(fault):
    source, evidence, _ = existing.prepare(decision=SourceEvidenceDecision.INSUFFICIENT)
    result = layout_b2.extract_b2(evidence)
    if fault == "gate_copy":
        object.__setattr__(result.pre_resolution_disposition, "gate_result", replace(evidence.gate_result))
    elif fault == "wrong_state":
        object.__setattr__(result.pre_resolution_disposition, "state", PolicyState.FAILED)
    elif fault == "sufficient_gate":
        object.__setattr__(evidence.gate_result, "decision", SourceEvidenceDecision.SUFFICIENT)
    else:
        object.__setattr__(result, "pre_resolution_disposition", None)
    with no_upstream(), pytest.raises(ValueError) as caught:
        retained(source, evidence, result)
    existing.assert_safe_failure(caught.value)


@pytest.mark.parametrize("changes", [
    {"consumer_mode": "LIVE"}, {"request_id": "participant-001"}, {"request_id": ""},
    {"image_id": "other-image"}, {"producer_id": "annotation-001"}, {"alias_namespace": "A" * 32},
])
def test_invalid_context_rejects_before_result_validation(changes):
    source, evidence, _ = existing.prepare()
    result = layout_b2.extract_b2(evidence)
    with no_upstream(), patch.object(projection, "_validate_result") as later, pytest.raises(ValueError) as caught:
        retained(source, evidence, result, **changes)
    later.assert_not_called()
    existing.assert_safe_failure(caught.value)


def test_independent_consumer_expected_ids_reject_emitted_bytes():
    source, evidence, _ = existing.prepare()
    raw = retained(source, evidence, layout_b2.extract_b2(evidence))
    for context, expected in [({"request": "other-request"}, "REJECT_REQUEST_ID_MISMATCH"),
                              ({"image": "other-image"}, "REJECT_IMAGE_ID_MISMATCH")]:
        with pytest.raises(ConformanceViolation) as caught:
            existing.validated(raw, **context)
        assert caught.value.code == expected


@pytest.mark.parametrize("options,code", [
    ({"date": "13/10/2026"}, "REJECT_INVALID_DATE"),
    ({"quantity": "0"}, "REJECT_INVALID_QUANTITY"),
    ({"quantity": "01"}, "REJECT_INVALID_QUANTITY"),
    ({"quantity": "1.0000"}, "REJECT_INVALID_QUANTITY"),
    ({"unit": "$5.50"}, "REJECT_CURRENCY_MISMATCH"),
    ({"unit": "RM 01.00"}, "REJECT_VALUE_RELATIONSHIP"),
])
def test_genuine_nonrepresentable_b2_values_reject_without_repair(options, code):
    source, evidence, _ = existing.prepare(**options)
    result = layout_b2.extract_b2(evidence)
    before = asdict(result)
    with no_upstream(), pytest.raises(ConformanceViolation) as caught:
        retained(source, evidence, result)
    assert caught.value.code == code
    assert caught.value.detail == "Synthetic projection rejected."
    assert before == asdict(result)
    existing.assert_safe_failure(caught.value)


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("reason,code", [
    ("MILK", "REJECT_UNSAFE_PROVENANCE"), ("Unable to read MILK during capture.", "REJECT_UNSAFE_PROVENANCE"),
    ("Synthetic source structure was unavailable. ", "REJECT_UNSAFE_PROVENANCE"),
    ("Unapproved generic reason.", "REJECT_UNSAFE_PROVENANCE"),
    ("\u00a0", "REJECT_UNSAFE_PROVENANCE"), ("", "REJECT_GATE_STATE"),
    ("OCR:failed", "REJECT_UNSAFE_PROVENANCE"),
])
def test_j04_vocabulary_and_v1_first_rejection_are_preserved(decision, reason, code):
    source, evidence, _ = existing.prepare(decision=decision, reasons=(reason,))
    result = layout_b2.extract_b2(evidence)
    before = asdict(evidence)
    with no_upstream(), pytest.raises(ConformanceViolation) as caught:
        retained(source, evidence, result)
    assert (caught.value.code, caught.value.path) == (code, "$.sourceGate.reasons[0]")
    assert before == asdict(evidence)
    existing.assert_safe_failure(caught.value)


@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("reason", existing.APPROVED_REASONS)
def test_reviewed_prose_short_tokens_and_complete_transcription_veto(decision, reason):
    source, evidence, _ = existing.prepare(decision=decision, reasons=(reason,))
    result = layout_b2.extract_b2(evidence)
    assert {"1", "x"} <= {token.original_text for token in source.tokens}
    with no_upstream():
        assert existing.validated(retained(source, evidence, result)).source_gate.reasons == (reason,)
    tokens = (replace(source.tokens[0], original_text=reason),) + source.tokens[1:]
    source = replace(source, tokens=tokens)
    evidence = replace(evidence, tokens=tokens)
    result = layout_b2.extract_b2(evidence)
    with no_upstream(), pytest.raises(ConformanceViolation) as caught:
        retained(source, evidence, result)
    assert caught.value.code == "REJECT_UNSAFE_PROVENANCE"


@pytest.mark.parametrize("code", existing.APPROVED_CODES)
def test_all_36_verified_diagnostics_keep_only_safe_metadata(code):
    source, evidence, _ = existing.prepare()
    result = layout_b2.extract_b2(evidence)
    error = ConformanceViolation(code, "$", "SECRET file:///tmp/participant-001.jpg")
    error.add_note("SECRET upstream note")
    with no_upstream(), patch.object(projection, "decode_and_validate_presentation_v1", side_effect=error), \
         pytest.raises(ConformanceViolation) as caught:
        retained(source, evidence, result)
    assert caught.value is not error
    assert (caught.value.code, caught.value.path, caught.value.detail) == (code, "$", "Synthetic projection rejected.")
    assert not getattr(caught.value, "__notes__", ())
    existing.assert_safe_failure(caught.value)


@pytest.mark.parametrize("code,path,safe", [
    ("REJECT_INVALID_JSON", "$.receipt.itemRows[0].fields[2].sourceTokenIds[0]", True),
    ("REJECT_INVALID_JSON", "$context.expectedImageId", True),
    ("REJECT_INVALID_JSON", "$.sourceGate.reasons[0]", True),
    ("REJECT_INVALID_JSON", "$.sourceEvidence.tokenIds[999]", False),
    ("REJECT_INVALID_JSON", "$.receipt.itemRows[00].rowId", False),
    ("REJECT_INVALID_JSON", "$.sourceGate.reasons[\u0660]", False),
    ("REJECT_INVALID_JSON", "$.SECRET", False),
    ("REJECT_SECRET", "$", False),
    ("SECRET file:///tmp/participant-001.jpg", "$", False),
    ("REJECT_INVALID_JSON", "$.private:receipt", False),
])
def test_structural_bounds_and_private_exception_chains(code, path, safe):
    source, evidence, _ = existing.prepare(reasons=existing.APPROVED_REASONS[:1])
    result = layout_b2.extract_b2(evidence)
    try:
        raise RuntimeError("SECRET original context")
    except RuntimeError as cause:
        try:
            raise ConformanceViolation(code, path, "SECRET private detail") from cause
        except ConformanceViolation as original:
            error = original
    with no_upstream(), patch.object(projection, "decode_and_validate_presentation_v1", side_effect=error), \
         pytest.raises(ValueError if safe else RuntimeError) as caught:
        retained(source, evidence, result)
    if safe:
        assert type(caught.value) is ConformanceViolation
        assert (caught.value.code, caught.value.path) == (code, path)
    else:
        assert type(caught.value) is RuntimeError
        assert caught.value.args == ("Synthetic projection failed.",)
    existing.assert_safe_failure(caught.value)


@pytest.mark.parametrize("changes,reason,pre_b2", [
    ({"consumer_mode": "LIVE"}, None, True), ({"image_id": "other-image"}, None, True),
    ({"alias_namespace": "A" * 32}, None, True), ({}, "", False),
    ({}, "Unapproved generic reason.", False),
])
def test_extracting_api_preserves_accepted_validation_order_and_exceptions(changes, reason, pre_b2, accepted_l02):
    source, evidence, _ = existing.prepare(reasons=() if reason is None else (reason,))
    arguments = dict(adapted_source=source, source_evidence=evidence, request_id=existing.REQUEST,
                     image_id=existing.IMAGE, alias_namespace=existing.NAMESPACE,
                     producer_id=existing.PRODUCER, consumer_mode="FIXTURE")
    arguments.update(changes)
    failures = []
    for module in (accepted_l02, projection):
        with patch.object(module, "extract_b2", wraps=layout_b2.extract_b2) as b2, pytest.raises(ValueError) as caught:
            module.extract_b2_fixture_presentation_v1(**arguments)
        assert b2.call_count == (0 if pre_b2 else 1)
        failures.append((type(caught.value), caught.value.args,
                         getattr(caught.value, "code", None), getattr(caught.value, "path", None)))
        existing.assert_safe_failure(caught.value)
    assert failures[0] == failures[1]


def test_serialized_bytes_validated_before_return_with_no_external_side_effects(capsys):
    source, evidence, _ = existing.prepare(quantity="0.750", unit="RM 1,234.50", receipt_total="MYR 23.90")
    result = layout_b2.extract_b2(evidence)
    before = asdict(source), asdict(evidence), asdict(result)
    with no_upstream(), ExitStack() as stack:
        for target in ("builtins.open", "pathlib.Path.open", "os.open", "socket.socket", "subprocess.Popen"):
            stack.enter_context(patch(target, side_effect=AssertionError("External side effect.")))
        validator = stack.enter_context(patch.object(projection, "decode_and_validate_presentation_v1",
                                                     wraps=decode_and_validate_presentation_v1))
        raw = retained(source, evidence, result)
    validator.assert_called_once_with(raw, expected_request_id=existing.REQUEST,
                                     expected_image_id=existing.IMAGE, consumer_mode="FIXTURE")
    wire = json.loads(raw)
    assert raw == json.dumps(wire, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    fields = wire["receipt"]["itemRows"][0]["fields"]
    assert fields[1]["originalAutomaticValue"] == fields[1]["presentationValue"] == "0.750"
    assert fields[2]["originalAutomaticValue"] == "RM 1,234.50" and fields[2]["presentationValue"] == "1234.50"
    assert all(field["nativeConfidence"] is None for field in fields)
    for private in ("private:", "participant-001", "file:///", "private-original-source-system", "rec_texts", "polygon"):
        assert private not in raw.decode()
    assert before == (asdict(source), asdict(evidence), asdict(result))
    assert capsys.readouterr() == ("", "")


def test_exact_public_signatures_and_missing_argument_never_trigger_execution():
    signature = inspect.signature(projection.project_retained_b2_fixture_presentation_v1)
    assert list(signature.parameters) == ["adapted_source", "source_evidence", "b2_result", "request_id",
                                          "image_id", "alias_namespace", "producer_id", "consumer_mode"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is inspect.Parameter.empty
               for parameter in signature.parameters.values())
    assert list(inspect.signature(projection.extract_b2_fixture_presentation_v1).parameters) == [
        "adapted_source", "source_evidence", "request_id", "image_id", "alias_namespace", "producer_id", "consumer_mode",
    ]
    with no_upstream(), pytest.raises(TypeError):
        projection.project_retained_b2_fixture_presentation_v1()
