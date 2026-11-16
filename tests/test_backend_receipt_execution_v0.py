"""Synthetic control-flow tests; gate doubles specify no operational criteria."""

from __future__ import annotations

import ast
import builtins
from copy import deepcopy
import inspect
from unittest.mock import Mock, patch

import pytest

import pipeline.backend_receipt_execution_v0 as execution
from pipeline.contracts import (
    OutputStage,
    PolicyState,
    ReceiptExtractionStatus,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
)
from pipeline.layout_b2 import B2ExtractionResult, extract_b2
from pipeline.ocr_adapter import (
    AdaptedOcrSource,
    OcrAdapterError,
    adapt_paddleocr_result,
    attach_gate_result,
)


def synthetic_source(*, status=SourceProcessingStatus.OCR_COMPLETED):
    regions = (
        ("PANTRYPROOF TEST MART", 20, 0, 180),
        ("DATE:", 10, 20, 45),
        ("2026-10-13", 70, 20, 90),
        ("MILK", 10, 45, 45),
        ("2", 110, 45, 10),
        ("x", 130, 45, 8),
        ("5.50", 155, 45, 38),
        ("11.00", 220, 45, 45),
        ("TOTAL", 130, 95, 55),
        ("11.00", 220, 95, 45),
    )
    return adapt_paddleocr_result(
        {
            "rec_texts": [text for text, *_ in regions],
            "rec_scores": [None, -0.0, 0.75, 0.99, None, 0.8, 0.9, 0.7, 0.95, 0.98],
            "rec_boxes": [[x, y, x + width, y + 10] for _, x, y, width in regions],
        },
        receipt_id="synthetic-l01-receipt",
        image_id="synthetic-l01-image",
        source_system="synthetic-l01-test",
        source_reference="synthetic-l01-source",
        processing_status=status,
    )


def synthetic_gate(source, decision=SourceEvidenceDecision.SUFFICIENT):
    return SourceEvidenceGateResult(
        gate_result_id="synthetic-l01-gate",
        receipt_id=source.receipt_id,
        decision=decision,
        reasons=("Synthetic gate double records insufficiency.",)
        if decision is SourceEvidenceDecision.INSUFFICIENT else (),
    )


def test_sufficient_execution_order_exact_calls_and_real_result_continuity():
    source = synthetic_source()
    gate = synthetic_gate(source)
    events = []
    captured = {}

    def evaluate(actual_source):
        assert actual_source is source
        events.append("gate")
        return gate

    def attach(actual_source, actual_gate):
        assert actual_source is source
        assert actual_gate is gate
        events.append("attach")
        captured["evidence"] = attach_gate_result(actual_source, actual_gate)
        return captured["evidence"]

    def extract(evidence):
        assert evidence is captured["evidence"]
        events.append("b2")
        captured["result"] = extract_b2(evidence)
        return captured["result"]

    evaluator = Mock(side_effect=evaluate)
    with patch.object(execution, "attach_gate_result", side_effect=attach) as attachment:
        with patch.object(execution, "extract_b2", side_effect=extract) as extractor:
            result = execution.extract_adapted_receipt_v0(
                adapted_source=source, gate_evaluator=evaluator
            )
    assert events == ["gate", "attach", "b2"]
    evaluator.assert_called_once_with(source)
    attachment.assert_called_once_with(source, gate)
    extractor.assert_called_once_with(captured["evidence"])
    assert type(result) is B2ExtractionResult
    assert result is captured["result"]
    assert result.receipt_output.source_evidence is captured["evidence"]
    assert captured["evidence"].gate_result is gate
    assert result.receipt_output.output_stage is OutputStage.PRE_REVIEW_AUTOMATIC
    assert result.receipt_output.extraction_status is ReceiptExtractionStatus.EXTRACTED
    assert result.receipt_output.store_name.value == "PANTRYPROOF TEST MART"
    assert result.receipt_output.purchase_date.value == "2026-10-13"
    assert result.receipt_output.receipt_total.value == "11.00"
    assert tuple(f.value for f in result.receipt_output.items[0].fields) == (
        "MILK", "2", "5.50", "11.00"
    )


def test_insufficient_gate_returns_real_b2_fallback_without_output_or_retry():
    source = synthetic_source()
    gate = synthetic_gate(source, SourceEvidenceDecision.INSUFFICIENT)
    evaluator = Mock(return_value=gate)
    with patch.object(execution, "extract_b2", wraps=extract_b2) as extractor:
        result = execution.extract_adapted_receipt_v0(
            adapted_source=source, gate_evaluator=evaluator
        )
    evaluator.assert_called_once_with(source)
    extractor.assert_called_once()
    assert type(result) is B2ExtractionResult
    assert result.receipt_output is None
    assert result.pre_resolution_disposition.state is PolicyState.FALLBACK_NO_UPDATE
    assert result.pre_resolution_disposition.gate_result is gate
    evidence = extractor.call_args.args[0]
    assert evidence.tokens is source.tokens
    assert evidence.provenance is source.provenance
    assert evidence.gate_result is gate


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError, MemoryError])
def test_gate_exception_propagates_same_exception_without_attachment_or_b2(error_type):
    source = synthetic_source()
    error = error_type("synthetic gate failure")
    evaluator = Mock(side_effect=error)
    with patch.object(execution, "attach_gate_result") as attachment:
        with patch.object(execution, "extract_b2") as extractor:
            with pytest.raises(error_type) as caught:
                execution.extract_adapted_receipt_v0(
                    adapted_source=source, gate_evaluator=evaluator
                )
    assert caught.value is error
    evaluator.assert_called_once_with(source)
    attachment.assert_not_called()
    extractor.assert_not_called()


@pytest.mark.parametrize("invalid", [None, {}, "SUFFICIENT", True, object()])
def test_invalid_gate_result_type_is_rejected_by_attachment_before_b2(invalid):
    source = synthetic_source()
    evaluator = Mock(return_value=invalid)
    with patch.object(execution, "attach_gate_result", wraps=attach_gate_result) as attachment:
        with patch.object(execution, "extract_b2") as extractor:
            with pytest.raises(OcrAdapterError):
                execution.extract_adapted_receipt_v0(
                    adapted_source=source, gate_evaluator=evaluator
                )
    evaluator.assert_called_once_with(source)
    attachment.assert_called_once_with(source, invalid)
    extractor.assert_not_called()


def test_mismatched_gate_receipt_is_rejected_without_b2():
    source = synthetic_source()
    gate = SourceEvidenceGateResult(
        "synthetic-foreign-gate", "synthetic-other-receipt",
        SourceEvidenceDecision.SUFFICIENT,
    )
    evaluator = Mock(return_value=gate)
    with patch.object(execution, "extract_b2") as extractor:
        with pytest.raises(OcrAdapterError, match="receipt_id does not match"):
            execution.extract_adapted_receipt_v0(
                adapted_source=source, gate_evaluator=evaluator
            )
    evaluator.assert_called_once_with(source)
    extractor.assert_not_called()


@pytest.mark.parametrize("decision", ["SUFFICIENT", "INSUFFICIENT", None, True])
def test_non_enum_gate_decision_cannot_bypass_b2_insufficient_branch(decision):
    source = synthetic_source()
    gate = SourceEvidenceGateResult("synthetic-gate", source.receipt_id, decision)
    evaluator = Mock(return_value=gate)
    with patch.object(execution, "extract_b2") as extractor:
        with pytest.raises(OcrAdapterError, match="SourceEvidenceDecision"):
            execution.extract_adapted_receipt_v0(
                adapted_source=source, gate_evaluator=evaluator
            )
    evaluator.assert_called_once_with(source)
    extractor.assert_not_called()


@pytest.mark.parametrize("attribute,value", [
    ("gate_result_id", ""),
    ("reasons", ("duplicate", "duplicate")),
    ("decision", SourceEvidenceDecision.INSUFFICIENT),
])
def test_existing_gate_record_validation_runs_before_b2(attribute, value):
    source = synthetic_source()
    gate = synthetic_gate(source)
    object.__setattr__(gate, attribute, value)
    evaluator = Mock(return_value=gate)
    with patch.object(execution, "extract_b2") as extractor:
        with pytest.raises(ValueError):
            execution.extract_adapted_receipt_v0(
                adapted_source=source, gate_evaluator=evaluator
            )
    evaluator.assert_called_once_with(source)
    extractor.assert_not_called()


def test_attachment_exception_propagates_without_b2_or_partial_return():
    source = synthetic_source()
    evaluator = Mock(return_value=synthetic_gate(source))
    error = OcrAdapterError("synthetic attachment failure")
    with patch.object(execution, "attach_gate_result", side_effect=error) as attachment:
        with patch.object(execution, "extract_b2") as extractor:
            with pytest.raises(OcrAdapterError) as caught:
                execution.extract_adapted_receipt_v0(
                    adapted_source=source, gate_evaluator=evaluator
                )
    assert caught.value is error
    evaluator.assert_called_once_with(source)
    attachment.assert_called_once()
    extractor.assert_not_called()


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError, MemoryError])
def test_b2_exception_propagates_same_exception_without_retry_or_partial_return(error_type):
    source = synthetic_source()
    evaluator = Mock(return_value=synthetic_gate(source))
    error = error_type("synthetic B2 failure")
    with patch.object(execution, "attach_gate_result", wraps=attach_gate_result) as attachment:
        with patch.object(execution, "extract_b2", side_effect=error) as extractor:
            with pytest.raises(error_type) as caught:
                execution.extract_adapted_receipt_v0(
                    adapted_source=source, gate_evaluator=evaluator
                )
    assert caught.value is error
    evaluator.assert_called_once_with(source)
    attachment.assert_called_once()
    extractor.assert_called_once()


@pytest.mark.parametrize("status", list(SourceProcessingStatus))
def test_source_identity_content_geometry_provenance_and_missing_confidence_are_preserved(status):
    # A synthetic gate double exercises status preservation, not OCR success policy.
    source = synthetic_source(status=status)
    original = deepcopy(source)
    gate = synthetic_gate(source)
    original_gate = deepcopy(gate)
    result = execution.extract_adapted_receipt_v0(
        adapted_source=source, gate_evaluator=Mock(return_value=gate)
    )
    evidence = result.receipt_output.source_evidence
    assert source == original
    assert gate == original_gate
    assert evidence.receipt_id == source.receipt_id
    assert evidence.image_id == source.image_id
    assert evidence.processing_status is status
    assert evidence.provenance is source.provenance
    assert evidence.tokens is source.tokens
    assert evidence.gate_result is gate
    for before, after in zip(source.tokens, evidence.tokens, strict=True):
        assert after is before
        assert after.polygon is before.polygon
        assert after.original_text == before.original_text
        assert after.raw_confidence == before.raw_confidence
    assert evidence.tokens[0].raw_confidence is None
    assert str(evidence.tokens[1].raw_confidence) == "-0.0"
    assert all(f.confidence is None for f in (
        result.receipt_output.store_name,
        result.receipt_output.purchase_date,
        result.receipt_output.receipt_total,
        *result.receipt_output.items[0].fields,
    ))


def test_repeated_independent_invocations_are_deterministic_and_each_call_executes_once():
    source = synthetic_source()
    before = deepcopy(source)
    gate = synthetic_gate(source)
    evaluator = Mock(return_value=gate)
    with patch.object(execution, "extract_b2", wraps=extract_b2) as extractor:
        first = execution.extract_adapted_receipt_v0(
            adapted_source=source, gate_evaluator=evaluator
        )
        second = execution.extract_adapted_receipt_v0(
            adapted_source=source, gate_evaluator=evaluator
        )
    assert first == second
    assert first is not second
    assert source == before
    assert evaluator.call_count == extractor.call_count == 2
    assert all(call.args[0] is source for call in evaluator.call_args_list)
    assert first.receipt_output.source_evidence.gate_result is gate
    assert second.receipt_output.source_evidence.gate_result is gate


@pytest.mark.parametrize("invalid", [None, {}, "source", object()])
def test_invalid_source_type_prevents_gate_and_b2(invalid):
    evaluator = Mock()
    with patch.object(execution, "extract_b2") as extractor:
        with pytest.raises(OcrAdapterError):
            execution.extract_adapted_receipt_v0(
                adapted_source=invalid, gate_evaluator=evaluator
            )
    evaluator.assert_not_called()
    extractor.assert_not_called()


def test_invalidated_adapted_source_is_rejected_before_gate():
    source = synthetic_source()
    object.__setattr__(source, "tokens", (source.tokens[0], source.tokens[0]))
    evaluator = Mock()
    with patch.object(execution, "extract_b2") as extractor:
        with pytest.raises(OcrAdapterError, match="unique"):
            execution.extract_adapted_receipt_v0(
                adapted_source=source, gate_evaluator=evaluator
            )
    evaluator.assert_not_called()
    extractor.assert_not_called()


@pytest.mark.parametrize("invalid", [None, 42])
def test_non_callable_evaluator_is_rejected_without_b2(invalid):
    with patch.object(execution, "extract_b2") as extractor:
        with pytest.raises(TypeError, match="callable"):
            execution.extract_adapted_receipt_v0(
                adapted_source=synthetic_source(), gate_evaluator=invalid
            )
    extractor.assert_not_called()


def test_valid_sufficient_empty_source_preserves_structural_failed_extraction():
    source = adapt_paddleocr_result(
        {"rec_texts": []}, receipt_id="synthetic-empty-receipt",
        image_id="synthetic-empty-image", source_system="synthetic-l01-test",
        source_reference="synthetic-empty-source",
        processing_status=SourceProcessingStatus.OCR_PARTIAL,
    )
    gate = synthetic_gate(source)
    result = execution.extract_adapted_receipt_v0(
        adapted_source=source, gate_evaluator=Mock(return_value=gate)
    )
    assert result.receipt_output is not None
    assert result.receipt_output.extraction_status is ReceiptExtractionStatus.FAILED
    assert result.receipt_output.items == ()
    assert result.receipt_output.source_evidence.tokens is source.tokens
    assert result.pre_resolution_disposition is None


def test_public_interface_is_keyword_only_and_uses_existing_records():
    signature = inspect.signature(execution.extract_adapted_receipt_v0)
    assert tuple(signature.parameters) == ("adapted_source", "gate_evaluator")
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in signature.parameters.values())
    assert execution.__all__ == ("extract_adapted_receipt_v0",)


def test_no_automatic_other_pipeline_transport_or_inventory_dependencies():
    tree = ast.parse(inspect.getsource(execution))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imported == {
        "__future__", "collections.abc", "pipeline.contracts",
        "pipeline.layout_b2", "pipeline.ocr_adapter",
    }
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    forbidden = (
        "paddle", "paddleocr", "paddlex", "pipeline.baseline_b1",
        "pipeline.baseline_b3", "pipeline.proposed", "pipeline.presentation_v1",
        "socket", "http", "sqlite3",
    )
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden):
            raise AssertionError("unexpected dependency: " + name)
        return original_import(name, *args, **kwargs)

    source = synthetic_source()
    with patch("builtins.__import__", side_effect=guarded_import):
        result = execution.extract_adapted_receipt_v0(
            adapted_source=source, gate_evaluator=Mock(return_value=synthetic_gate(source))
        )
    assert type(result) is B2ExtractionResult
