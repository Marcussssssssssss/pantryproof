"""Controlled synthetic coordinator acceptance, not backend fault evidence.

Fixture preparation uses the real adapter only. Gate, attachment, B2 and
projection counts below belong to one coordinated invocation. Boundary faults
are explicit test injections, not claims of real algorithm defects.
"""

from contextlib import ExitStack
from dataclasses import FrozenInstanceError, asdict, fields, replace
import ast
import hashlib
import inspect
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pipeline import backend_synthetic_coordinator_v0 as coordinator
from pipeline import backend_receipt_execution_v0 as l01
from pipeline import baseline_b1, baseline_b3, layout_b2, ocr_adapter
from pipeline.contracts import (
    OutputStage, PolicyState, ReceiptExtractionStatus, SourceEvidenceDecision,
    SourceEvidenceGateResult, SourceProcessingStatus,
)
from pipeline.presentation_v1 import b2_synthetic_projection_v0 as s01
from pipeline.presentation_v1 import synthetic_failure_projection_v0 as l03
from pipeline.presentation_v1.conformance import ConformanceViolation, decode_and_validate_presentation_v1


Reason = coordinator.SyntheticCoordinatorRejectionReasonV0
Case = l03.SyntheticFailureCaseV0
Deferred = l03.SyntheticDeferredEventV0.POST_INSUFFICIENT_PRESENTATION_EXCEPTION
SAFE = (
    "Synthetic source structure was unavailable.", "There is 1 unreadable row.",
    "The x marker was unavailable.", "Extraction could not locate 1 safe heading.",
)
REQUEST = "request-s02-synthetic"
IMAGE = "image-s02-synthetic"
NAMESPACE = "0123456789abcdef0123456789abcdef"
PRODUCER = "I2B_SYNTHETIC_S02"


class BoundaryFault(Exception):
    """Unexpected controlled fault outside S01's known rejection surfaces."""


def context(**changes):
    return replace(l03.SyntheticFailureContextV0(REQUEST, IMAGE, NAMESPACE, "FIXTURE"), **changes)


def source(status=SourceProcessingStatus.OCR_COMPLETED, *, empty=False):
    regions = [] if empty else [
        ("SECRET SYNTHETIC MART", 20, 0, 180), ("DATE:", 10, 20, 45),
        ("2026-11-18", 70, 20, 100), ("MILK", 10, 45, 45),
        ("1", 110, 45, 10), ("x", 130, 45, 8), ("5.50", 155, 45, 38),
        ("5.50", 220, 45, 45), ("TOTAL", 130, 95, 55), ("5.50", 220, 95, 70),
    ]
    return ocr_adapter.adapt_paddleocr_result(
        {"rec_texts": [text for text, *_ in regions],
         "rec_boxes": [[x, y, x + width, y + 10] for _, x, y, width in regions],
         "rec_scores": [(None, -0.0, 0.75)[index % 3] for index in range(len(regions))]},
        receipt_id="private:receipt:s02", image_id=IMAGE, source_system="private-original-system",
        source_reference="file:///tmp/participant-001.jpg", processing_status=status,
    )


def exercise(*, status=SourceProcessingStatus.OCR_COMPLETED, decision=SourceEvidenceDecision.SUFFICIENT,
             empty=False, declaration=None, fault=None, error=None, reasons=SAFE[:1],
             gate_transform=None, evidence_transform=None, result_transform=None, projection_transform=None, changes=None):
    """Arrange genuine records, then observe exactly one invocation."""
    a = source(status, empty=empty)
    g = SourceEvidenceGateResult("private:gate:s02", a.receipt_id, decision, reasons)
    before = asdict(a), asdict(g)
    captured = {"source": a, "gate": g}
    events = []

    def evaluate(actual):
        events.append("gate")
        assert actual is a
        if fault == "gate":
            raise error
        returned = g if gate_transform is None else gate_transform(g)
        captured["returned_gate"] = returned
        return returned

    def attach(actual, gate):
        events.append("attach")
        if fault == "attach":
            raise error
        e = ocr_adapter.attach_gate_result(actual, gate)
        e = e if evidence_transform is None else evidence_transform(e)
        captured["evidence"] = e
        return e

    def extract(e):
        events.append("b2")
        if fault == "b2":
            raise error
        r = layout_b2.extract_b2(e)
        r = r if result_transform is None else result_transform(r)
        captured["b2"] = r
        return r

    def project(**kwargs):
        events.append("project")
        if fault == "project":
            raise error
        raw = s01.project_retained_b2_fixture_presentation_v1(**kwargs)
        raw = raw if projection_transform is None else projection_transform(raw)
        captured["payload"] = raw
        return raw

    evaluator = Mock(side_effect=evaluate)
    arguments = dict(adapted_source=a, gate_evaluator=evaluator, context=context(), producer_id=PRODUCER,
                     expected_synthetic_failure=declaration)
    arguments.update(changes or {})
    with patch.object(coordinator, "attach_gate_result", side_effect=attach) as attachment, \
         patch.object(coordinator, "extract_b2", side_effect=extract) as b2, \
         patch.object(coordinator, "project_retained_b2_fixture_presentation_v1", side_effect=project) as projection, \
         patch.object(coordinator, "build_synthetic_failure_presentation_v1",
                      wraps=l03.build_synthetic_failure_presentation_v1) as failure:
        returned = coordinator.coordinate_synthetic_receipt_v0(**arguments)
    captured.update(events=events, counts=(evaluator.call_count, attachment.call_count, b2.call_count,
                                          projection.call_count, failure.call_count), evaluator=evaluator,
                    before=before)
    return returned, captured


def local(result, reason):
    assert type(result) is coordinator.SyntheticCoordinatorResultV0
    assert type(result.result) is coordinator.SyntheticCoordinatorRejectionV0
    assert result.result.reason is reason
    for value in (result, result.trace, result.result):
        assert not hasattr(value, "__dict__")
        assert not hasattr(value, "__cause__") and not hasattr(value, "__context__")
        for private in ("SECRET", "private:", "file:///", "participant-001", "MILK"):
            assert private not in repr(value)
    return result.trace


def validated(result):
    assert type(result.result) is bytes
    return decode_and_validate_presentation_v1(
        result.result, expected_request_id=REQUEST, expected_image_id=IMAGE, consumer_mode="FIXTURE",
    )


@pytest.mark.parametrize("status", list(SourceProcessingStatus))
@pytest.mark.parametrize("decision", list(SourceEvidenceDecision))
@pytest.mark.parametrize("empty", [False, True])
def test_genuine_success_all_permitted_statuses_counts_identity_and_no_mutation(status, decision, empty):
    result, observed = exercise(status=status, decision=decision, empty=empty)
    dto = validated(result)
    trace = result.trace
    assert observed["events"] == ["gate", "attach", "b2", "project"]
    assert observed["counts"] == (1, 1, 1, 1, 0)
    assert trace.adapted_source is observed["source"]
    assert trace.gate_result is observed["gate"] is observed["returned_gate"]
    assert trace.source_evidence is observed["evidence"]
    assert trace.b2_result is observed["b2"]
    assert trace.source_evidence.tokens is trace.adapted_source.tokens
    assert trace.source_evidence.provenance is trace.adapted_source.provenance
    assert trace.source_evidence.gate_result is trace.gate_result
    assert result.result is observed["payload"]
    assert observed["before"] == (asdict(trace.adapted_source), asdict(trace.gate_result))
    assert dto.source_evidence.source_processing_status == status.value
    if decision is SourceEvidenceDecision.SUFFICIENT:
        assert dto.outcome.status == "RESULT_AVAILABLE"
        assert trace.b2_result.receipt_output.source_evidence is trace.source_evidence
        assert dto.automatic_extraction.extraction_status == trace.b2_result.receipt_output.extraction_status.value
        if empty:
            assert trace.b2_result.receipt_output.extraction_status is ReceiptExtractionStatus.FAILED
    else:
        assert dto.outcome.status == "SOURCE_EVIDENCE_INSUFFICIENT"
        assert dto.receipt is dto.automatic_extraction is None
        assert trace.b2_result.pre_resolution_disposition.gate_result is trace.gate_result
    assert dto.outcome.failure is None


@pytest.mark.parametrize("stage,reason,counts", [
    ("gate", Reason.GATE_EXCEPTION, (1, 0, 0, 0, 0)),
    ("attach", Reason.ATTACHMENT_REJECTED, (1, 1, 0, 0, 0)),
    ("b2", Reason.B2_EXCEPTION, (1, 1, 1, 0, 0)),
    ("project", Reason.PROJECTION_REJECTED, (1, 1, 1, 1, 0)),
])
def test_unclassified_observed_exception_stops_and_retains_original_facts(stage, reason, counts):
    result, observed = exercise(fault=stage, error=BoundaryFault("SECRET file:///tmp/participant-001.jpg"))
    trace = local(result, reason)
    assert observed["counts"] == counts
    assert trace.adapted_source is observed["source"]
    assert (trace.gate_result is None) is (stage == "gate")
    assert (trace.source_evidence is None) is (stage in ("gate", "attach"))
    assert (trace.b2_result is None) is (stage != "project")


@pytest.mark.parametrize("stage,declaration,wire_stage,counts", [
    ("gate", Case.SOURCE_GATE_EXECUTION_FAILURE, "SOURCE_GATE", (1, 0, 0, 0, 1)),
    ("b2", Case.EXTRACTION_ENGINE_FAILURE, "EXTRACTION", (1, 1, 1, 0, 1)),
    ("project", Case.PRESENTATION_PROJECTION_FAILURE, "PRESENTATION_ADAPTER", (1, 1, 1, 1, 1)),
])
@pytest.mark.parametrize("status", [SourceProcessingStatus.OCR_COMPLETED, SourceProcessingStatus.OCR_PARTIAL])
def test_matching_declared_and_observed_controlled_fault_uses_l03(stage, declaration, wire_stage, counts, status):
    result, observed = exercise(status=status, fault=stage, declaration=declaration,
                                error=BoundaryFault("SECRET injected boundary fault"))
    dto = validated(result)
    assert observed["counts"] == counts
    assert dto.outcome.status == "PROCESSING_FAILED"
    assert (dto.outcome.failure.stage, dto.outcome.failure.code, dto.outcome.failure.retryable) == (
        wire_stage, declaration.value, True,
    )
    assert dto.receipt is dto.automatic_extraction is None
    assert b"SECRET" not in result.result and b"private:" not in result.result
    assert result.trace.adapted_source is observed["source"]


@pytest.mark.parametrize("status", list(SourceProcessingStatus))
def test_explicit_insufficient_event_requires_observed_exception_and_returns_no_bytes(status):
    result, observed = exercise(status=status, decision=SourceEvidenceDecision.INSUFFICIENT,
                                fault="project", error=BoundaryFault("SECRET"), declaration=Deferred)
    assert type(result.result) is l03.NoFailureEnvelopeV0
    assert result.result.reason is l03.NoFailureEnvelopeReasonV0.DEFERRED_POST_INSUFFICIENT
    assert not hasattr(result.result, "payload")
    assert observed["counts"] == (1, 1, 1, 1, 1)
    assert result.trace.b2_result.pre_resolution_disposition.gate_result is result.trace.gate_result


@pytest.mark.parametrize("declaration,counts", [
    (Case.SOURCE_GATE_EXECUTION_FAILURE, (1, 0, 0, 0, 0)),
    (Case.EXTRACTION_ENGINE_FAILURE, (1, 1, 1, 0, 0)),
    (Case.PRESENTATION_PROJECTION_FAILURE, (1, 1, 1, 1, 0)),
    (Deferred, (1, 1, 1, 1, 0)),
])
def test_declaration_does_not_inject_fault_and_stops_when_unobserved(declaration, counts):
    decision = SourceEvidenceDecision.INSUFFICIENT if declaration is Deferred else SourceEvidenceDecision.SUFFICIENT
    result, observed = exercise(declaration=declaration, decision=decision)
    local(result, Reason.SYNTHETIC_EVENT_NOT_OBSERVED)
    assert observed["counts"] == counts


@pytest.mark.parametrize("fault,declaration,reason,counts", [
    ("gate", Case.EXTRACTION_ENGINE_FAILURE, Reason.GATE_EXCEPTION, (1, 0, 0, 0, 0)),
    ("gate", Case.PRESENTATION_PROJECTION_FAILURE, Reason.GATE_EXCEPTION, (1, 0, 0, 0, 0)),
    ("attach", Case.EXTRACTION_ENGINE_FAILURE, Reason.ATTACHMENT_REJECTED, (1, 1, 0, 0, 0)),
    ("b2", Case.PRESENTATION_PROJECTION_FAILURE, Reason.B2_EXCEPTION, (1, 1, 1, 0, 0)),
    ("b2", Deferred, Reason.B2_EXCEPTION, (1, 1, 1, 0, 0)),
])
def test_actual_earlier_failure_wins_over_later_declared_event(fault, declaration, reason, counts):
    result, observed = exercise(fault=fault, declaration=declaration, error=BoundaryFault("SECRET"))
    local(result, reason)
    assert observed["counts"] == counts


@pytest.mark.parametrize("stage,declaration,reason", [
    ("gate", Case.SOURCE_GATE_EXECUTION_FAILURE, Reason.GATE_EXCEPTION),
    ("b2", Case.EXTRACTION_ENGINE_FAILURE, Reason.B2_EXCEPTION),
    ("project", Case.PRESENTATION_PROJECTION_FAILURE, Reason.PROJECTION_REJECTED),
])
@pytest.mark.parametrize("error_type", [ValueError, TypeError, ConformanceViolation])
def test_validation_families_stay_local_despite_matching_declaration(stage, declaration, reason, error_type):
    error = (ConformanceViolation("SECRET code", "$.private:source", "SECRET detail")
             if error_type is ConformanceViolation else error_type("SECRET validation"))
    result, observed = exercise(fault=stage, declaration=declaration, error=error)
    local(result, reason)
    assert observed["counts"][-1] == 0


@pytest.mark.parametrize("declaration,decision", [
    (Case.PRESENTATION_PROJECTION_FAILURE, SourceEvidenceDecision.SUFFICIENT),
    (Deferred, SourceEvidenceDecision.INSUFFICIENT),
])
def test_s01_sanitized_runtime_error_is_not_evidence_of_hidden_technical_cause(declaration, decision):
    result, observed = exercise(declaration=declaration, decision=decision, fault="project",
                                error=RuntimeError("Synthetic projection failed."))
    local(result, Reason.PROJECTION_REJECTED)
    assert observed["counts"] == (1, 1, 1, 1, 0)


@pytest.mark.parametrize("stage,declaration", [("gate", Case.SOURCE_GATE_EXECUTION_FAILURE),
                                             ("b2", Case.EXTRACTION_ENGINE_FAILURE)])
def test_declared_runtime_fault_at_upstream_call_is_distinct_from_s01_rejection(stage, declaration):
    result, observed = exercise(declaration=declaration, fault=stage, error=RuntimeError("SECRET controlled fault"))
    assert validated(result).outcome.failure.code == declaration.value
    assert observed["counts"][-1] == 1


@pytest.mark.parametrize("bad", [None, "private:bad", bytearray(b"{}"), b"{}", b"not JSON"])
def test_invalid_projection_return_never_becomes_payload_or_unobserved_success(bad):
    result, observed = exercise(projection_transform=lambda raw: bad,
                                declaration=Case.PRESENTATION_PROJECTION_FAILURE)
    local(result, Reason.PROJECTION_REJECTED)
    assert observed["counts"] == (1, 1, 1, 1, 0)


def test_valid_v1_wrong_outcome_from_projection_is_not_a_successful_s01_result():
    def wrong_outcome(raw):
        wire = json.loads(raw)
        wire["outcome"] = {"status": "PROCESSING_FAILED", "failure": {
            "stage": "EXTRACTION", "code": "EXTRACTION_ENGINE_FAILURE", "retryable": True,
        }}
        wire["automaticExtraction"] = wire["receipt"] = None
        return json.dumps(wire, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    result, observed = exercise(projection_transform=wrong_outcome)
    local(result, Reason.PROJECTION_REJECTED)
    assert observed["counts"] == (1, 1, 1, 1, 0)


@pytest.mark.parametrize("bad", [None, b"{}", l03.ValidatedFailureEnvelopeV0(b"{}"),
                                 l03.NoFailureEnvelopeV0("INVALID_INPUT")])
def test_unexpected_l03_result_is_not_trusted_as_validated_bytes(bad):
    with patch.object(l03, "build_synthetic_failure_presentation_v1", return_value=bad):
        result, observed = exercise(fault="gate", error=BoundaryFault("SECRET"),
                                    declaration=Case.SOURCE_GATE_EXECUTION_FAILURE)
    local(result, Reason.COORDINATOR_FAILED)
    assert observed["counts"] == (1, 0, 0, 0, 1)


def test_valid_l03_bytes_for_a_different_event_are_not_published():
    wrong = l03.build_synthetic_failure_presentation_v1(
        context=context(), failure=l03.SyntheticFailureFactsV0(
            REQUEST, IMAGE, Case.OCR_ENGINE_FAILURE, None, None, None, None,
        ),
    )
    assert type(wrong) is l03.ValidatedFailureEnvelopeV0
    with patch.object(l03, "build_synthetic_failure_presentation_v1", return_value=wrong):
        result, _ = exercise(fault="gate", error=BoundaryFault("SECRET"),
                             declaration=Case.SOURCE_GATE_EXECUTION_FAILURE)
    local(result, Reason.COORDINATOR_FAILED)


@pytest.mark.parametrize("declaration,decision,stage,reason", [
    (Case.PRESENTATION_PROJECTION_FAILURE, SourceEvidenceDecision.INSUFFICIENT, "project", Reason.PROJECTION_REJECTED),
    (Deferred, SourceEvidenceDecision.SUFFICIENT, "project", Reason.PROJECTION_REJECTED),
    (Case.EXTRACTION_ENGINE_FAILURE, SourceEvidenceDecision.INSUFFICIENT, "b2", Reason.B2_EXCEPTION),
])
def test_ineligible_sufficient_insufficient_combinations_never_relabel(declaration, decision, stage, reason):
    result, observed = exercise(declaration=declaration, decision=decision, fault=stage, error=BoundaryFault("SECRET"))
    local(result, reason)
    assert observed["counts"][-1] == 0


@pytest.mark.parametrize("status", [SourceProcessingStatus.RECEIVED, SourceProcessingStatus.OCR_FAILED])
@pytest.mark.parametrize("stage,declaration,reason", [
    ("gate", Case.SOURCE_GATE_EXECUTION_FAILURE, Reason.GATE_EXCEPTION),
    ("b2", Case.EXTRACTION_ENGINE_FAILURE, Reason.B2_EXCEPTION),
    ("project", Case.PRESENTATION_PROJECTION_FAILURE, Reason.PROJECTION_REJECTED),
])
def test_s06_ineligible_status_is_preserved_without_technical_emission(status, stage, declaration, reason):
    result, observed = exercise(status=status, fault=stage, declaration=declaration, error=BoundaryFault("SECRET"))
    local(result, reason)
    assert result.trace.adapted_source.processing_status is status
    assert observed["counts"][-1] == 0


@pytest.mark.parametrize("reason,expected", [("MILK", l03.NoFailureEnvelopeReasonV0.UNSAFE_GATE_REASON),
                                           ("", l03.NoFailureEnvelopeReasonV0.V1_VALIDATION_REJECTED)])
def test_l03_no_envelope_classification_is_preserved_unchanged(reason, expected):
    result, observed = exercise(declaration=Case.EXTRACTION_ENGINE_FAILURE, fault="b2",
                                error=BoundaryFault("SECRET"), reasons=(reason,))
    assert type(result.result) is l03.NoFailureEnvelopeV0
    assert result.result.reason is expected
    assert observed["counts"] == (1, 1, 1, 0, 1)


@pytest.mark.parametrize("value", [None, {}, "SUFFICIENT", True])
def test_invalid_gate_type_is_not_retained_or_attached(value):
    result, observed = exercise(gate_transform=lambda gate: value)
    trace = local(result, Reason.INVALID_GATE_RESULT)
    assert trace.gate_result is trace.source_evidence is trace.b2_result is None
    assert observed["counts"] == (1, 0, 0, 0, 0)


@pytest.mark.parametrize("fault", ["receipt", "duplicate_reasons", "missing_insufficient_reason"])
def test_admissible_invalid_gate_is_retained_without_attachment(fault):
    def corrupt(gate):
        if fault == "receipt":
            object.__setattr__(gate, "receipt_id", "foreign-receipt")
        elif fault == "duplicate_reasons":
            object.__setattr__(gate, "reasons", (SAFE[0], SAFE[0]))
        else:
            object.__setattr__(gate, "decision", SourceEvidenceDecision.INSUFFICIENT)
            object.__setattr__(gate, "reasons", ())
        return gate
    result, observed = exercise(gate_transform=corrupt)
    trace = local(result, Reason.INVALID_GATE_RESULT)
    assert trace.gate_result is observed["returned_gate"]
    assert observed["counts"] == (1, 0, 0, 0, 0)


@pytest.mark.parametrize("fault", ["tuple", "provenance", "gate", "status", "missing"])
def test_bad_attachment_retains_admissible_return_but_never_executes_b2(fault):
    def corrupt(evidence):
        if fault == "tuple":
            return replace(evidence, tokens=tuple(list(evidence.tokens)))
        if fault == "provenance":
            return replace(evidence, provenance=replace(evidence.provenance))
        if fault == "gate":
            return replace(evidence, gate_result=replace(evidence.gate_result))
        if fault == "status":
            return replace(evidence, processing_status=SourceProcessingStatus.OCR_PARTIAL)
        return None
    result, observed = exercise(evidence_transform=corrupt)
    trace = local(result, Reason.ATTACHMENT_REJECTED)
    assert trace.gate_result is observed["gate"]
    assert trace.source_evidence is observed["evidence"]
    assert observed["counts"] == (1, 1, 0, 0, 0)


@pytest.mark.parametrize("fault", ["missing", "mapping", "both", "neither", "foreign_evidence", "field_id", "unknown_token",
                                    "owner", "stage", "fallback_gate", "fallback_state"])
def test_invalid_returned_b2_result_never_reexecutes_or_projects(fault):
    insufficient = fault.startswith("fallback")

    def corrupt(result):
        if fault == "missing":
            return None
        if fault == "mapping":
            return {"private": "SECRET"}
        if fault == "both":
            from pipeline.contracts import PreResolutionDisposition
            object.__setattr__(result, "pre_resolution_disposition",
                               PreResolutionDisposition(PolicyState.REVIEW_REQUIRED, result.receipt_output.source_evidence.gate_result))
        elif fault == "neither":
            object.__setattr__(result, "receipt_output", None)
        elif fault == "foreign_evidence":
            object.__setattr__(result.receipt_output, "source_evidence", replace(result.receipt_output.source_evidence))
        elif fault == "field_id":
            object.__setattr__(result.receipt_output.purchase_date, "field_id", result.receipt_output.store_name.field_id)
        elif fault == "unknown_token":
            object.__setattr__(result.receipt_output.store_name, "source_token_ids", ("private:unknown",))
        elif fault == "owner":
            object.__setattr__(result.receipt_output, "receipt_id", "foreign-receipt")
        elif fault == "stage":
            object.__setattr__(result.receipt_output, "output_stage", OutputStage.HUMAN_REVIEWED)
        elif fault == "fallback_gate":
            object.__setattr__(result.pre_resolution_disposition, "gate_result", replace(result.pre_resolution_disposition.gate_result))
        else:
            object.__setattr__(result.pre_resolution_disposition, "state", PolicyState.FAILED)
        return result

    result, observed = exercise(decision=SourceEvidenceDecision.INSUFFICIENT if insufficient else SourceEvidenceDecision.SUFFICIENT,
                                result_transform=corrupt)
    trace = local(result, Reason.INVALID_B2_RESULT)
    assert trace.b2_result is (None if fault in ("missing", "mapping") else observed["b2"])
    assert observed["counts"] == (1, 1, 1, 0, 0)


class Hostile:
    def __getattribute__(self, name):
        raise AssertionError("Untrusted attribute.")
    def __eq__(self, other):
        raise AssertionError("Untrusted equality.")
    def __hash__(self):
        raise AssertionError("Untrusted hash.")
    def __iter__(self):
        raise AssertionError("Untrusted iteration.")
    def __str__(self):
        raise AssertionError("Untrusted str.")
    def __repr__(self):
        raise AssertionError("Untrusted repr.")


class HostileString(str):
    __eq__ = Hostile.__eq__
    __hash__ = Hostile.__hash__


@pytest.mark.parametrize("fault", [
    "outer_source", "outer_context", "missing_slot", "context_subclass", "source_subclass", "request", "image", "producer", "namespace",
    "mode", "source_status", "source_tuple", "source_point", "source_text", "source_duplicate", "source_owner", "source_image",
    "decl_string", "decl_hostile", "decl_unavailable", "decl_ocr", "evaluator", "confidence_bool",
])
def test_hostile_and_invalid_inputs_never_execute_upstream(fault):
    a = source()
    evaluator_spy = Mock()
    arguments = dict(adapted_source=a, gate_evaluator=evaluator_spy, context=context(), producer_id=PRODUCER)
    if fault == "outer_source":
        arguments["adapted_source"] = Hostile()
    elif fault == "outer_context":
        arguments["context"] = Hostile()
    elif fault == "missing_slot":
        arguments["context"] = object.__new__(l03.SyntheticFailureContextV0)
    elif fault == "context_subclass":
        class ForeignContext(l03.SyntheticFailureContextV0):
            __getattribute__ = Hostile.__getattribute__
        arguments["context"] = object.__new__(ForeignContext)
    elif fault == "source_subclass":
        class ForeignSource(ocr_adapter.AdaptedOcrSource):
            __getattribute__ = Hostile.__getattribute__
        arguments["adapted_source"] = object.__new__(ForeignSource)
    elif fault == "request":
        arguments["context"] = context(request_id=HostileString(REQUEST))
    elif fault == "image":
        arguments["context"] = context(image_id="other-image")
    elif fault == "producer":
        arguments["producer_id"] = "participant-001"
    elif fault == "namespace":
        arguments["context"] = context(alias_namespace="A" * 32)
    elif fault == "mode":
        arguments["context"] = context(consumer_mode="LIVE")
    elif fault == "source_status":
        object.__setattr__(a, "processing_status", "OCR_COMPLETED")
    elif fault == "source_tuple":
        object.__setattr__(a, "tokens", Hostile())
    elif fault == "source_point":
        object.__setattr__(a.tokens[0].polygon[0], "x", Hostile())
    elif fault == "source_text":
        object.__setattr__(a.tokens[0], "original_text", Hostile())
    elif fault == "source_duplicate":
        object.__setattr__(a, "tokens", (a.tokens[0], a.tokens[0]))
    elif fault == "source_owner":
        object.__setattr__(a.tokens[0], "receipt_id", "foreign-receipt")
    elif fault == "source_image":
        object.__setattr__(a, "image_id", "other-image")
    elif fault == "decl_string":
        arguments["expected_synthetic_failure"] = Case.EXTRACTION_ENGINE_FAILURE.value
    elif fault == "decl_hostile":
        arguments["expected_synthetic_failure"] = Hostile()
    elif fault == "decl_unavailable":
        arguments["expected_synthetic_failure"] = Case.PROCESSOR_NOT_AVAILABLE
    elif fault == "decl_ocr":
        arguments["expected_synthetic_failure"] = Case.OCR_ENGINE_FAILURE
    elif fault == "evaluator":
        arguments["gate_evaluator"] = Hostile()
    else:
        object.__setattr__(a.tokens[0], "raw_confidence", True)
    with patch.object(coordinator, "attach_gate_result") as attachment, patch.object(coordinator, "extract_b2") as b2, \
         patch.object(coordinator, "project_retained_b2_fixture_presentation_v1") as project:
        result = coordinator.coordinate_synthetic_receipt_v0(**arguments)
    local(result, Reason.INVALID_INPUT)
    evaluator_spy.assert_not_called()
    attachment.assert_not_called()
    b2.assert_not_called()
    project.assert_not_called()


@pytest.mark.parametrize("fault", ["gate", "attach", "b2"])
def test_hostile_returned_shapes_never_publish_or_retain_them(fault):
    transformations = {"gate": {"gate_transform": lambda value: Hostile()},
                       "attach": {"evidence_transform": lambda value: Hostile()},
                       "b2": {"result_transform": lambda value: Hostile()}}
    result, _ = exercise(**transformations[fault])
    expected = {"gate": Reason.INVALID_GATE_RESULT, "attach": Reason.ATTACHMENT_REJECTED, "b2": Reason.INVALID_B2_RESULT}
    trace = local(result, expected[fault])
    assert getattr(trace, {"gate": "gate_result", "attach": "source_evidence", "b2": "b2_result"}[fault]) is None


@pytest.mark.parametrize("declaration", [None, Case.PRESENTATION_PROJECTION_FAILURE])
@pytest.mark.parametrize("reason", ["MILK", "", "OCR:failed", "Unapproved generic reason."])
def test_actual_j04_or_v1_rejection_remains_local_even_with_declaration(declaration, reason):
    result, observed = exercise(declaration=declaration, reasons=(reason,))
    local(result, Reason.PROJECTION_REJECTED)
    assert observed["counts"] == (1, 1, 1, 1, 0)


def test_actual_s01_unsafe_diagnostic_rejection_does_not_turn_into_technical_envelope():
    error = ConformanceViolation("REJECT_SECRET", "$.private:receipt", "SECRET detail")
    with patch.object(s01, "decode_and_validate_presentation_v1", side_effect=error):
        result, observed = exercise(declaration=Case.PRESENTATION_PROJECTION_FAILURE)
    local(result, Reason.PROJECTION_REJECTED)
    assert observed["counts"] == (1, 1, 1, 1, 0)


class HostileFault(Exception):
    def __getattribute__(self, name):
        if name in ("code", "path", "detail", "args", "__cause__", "__context__", "__notes__", "__traceback__"):
            raise AssertionError("Private exception metadata access.")
        return super().__getattribute__(name)
    def __str__(self):
        raise AssertionError("Exception formatting.")
    def __repr__(self):
        raise AssertionError("Exception representation.")


@pytest.mark.parametrize("stage", ["gate", "attach", "b2", "project"])
def test_private_exception_metadata_causes_and_notes_never_escape(stage, capsys):
    try:
        raise ValueError("SECRET original context")
    except ValueError as cause:
        error = HostileFault("SECRET args")
        error.__cause__ = cause
        error.__context__ = cause
        object.__setattr__(error, "__notes__", ["SECRET note"])
    result, _ = exercise(fault=stage, error=error)
    assert type(result.result) is coordinator.SyntheticCoordinatorRejectionV0
    assert set(field.name for field in fields(result.result)) == {"reason"}
    assert capsys.readouterr() == ("", "")
    assert "SECRET" not in repr(result) + repr(result.trace) + repr(result.result)


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("stage", ["gate", "attach", "b2", "project"])
def test_interruption_is_not_a_processing_failure(signal, stage):
    with pytest.raises(signal):
        exercise(fault=stage, error=signal())


def test_earlier_rejection_prevents_later_faults_and_unexpected_internal_failure_is_fixed():
    with patch.object(coordinator, "_record_valid", side_effect=BoundaryFault("SECRET late")) as later:
        result, observed = exercise(changes={"context": context(consumer_mode="LIVE")})
    local(result, Reason.INVALID_INPUT)
    later.assert_not_called()
    assert observed["counts"] == (0, 0, 0, 0, 0)
    with patch.object(coordinator, "_record_valid", side_effect=BoundaryFault("SECRET internal")):
        result, observed = exercise()
    local(result, Reason.COORDINATOR_FAILED)
    assert observed["counts"] == (0, 0, 0, 0, 0)


def test_unexpected_final_verification_exception_is_coordinator_failed_not_v1_rejection():
    with patch.object(coordinator, "decode_and_validate_presentation_v1", side_effect=BoundaryFault("SECRET verifier")):
        result, observed = exercise()
    local(result, Reason.COORDINATOR_FAILED)
    assert observed["counts"] == (1, 1, 1, 1, 0)


def test_deterministic_bytes_match_retained_api_and_independent_consumer_contexts():
    first, _ = exercise()
    second, _ = exercise()
    assert first.result == second.result
    trace = first.trace
    assert first.result == s01.project_retained_b2_fixture_presentation_v1(
        adapted_source=trace.adapted_source, source_evidence=trace.source_evidence, b2_result=trace.b2_result,
        request_id=REQUEST, image_id=IMAGE, alias_namespace=NAMESPACE, producer_id=PRODUCER, consumer_mode="FIXTURE",
    )
    for request, image, expected in [("other-request", IMAGE, "REJECT_REQUEST_ID_MISMATCH"),
                                    (REQUEST, "other-image", "REJECT_IMAGE_ID_MISMATCH")]:
        with pytest.raises(ConformanceViolation) as caught:
            decode_and_validate_presentation_v1(first.result, expected_request_id=request,
                                                expected_image_id=image, consumer_mode="FIXTURE")
        assert caught.value.code == expected


def test_no_external_or_wrong_component_execution(capsys):
    a = source()
    gate = SourceEvidenceGateResult("private:gate:s02", a.receipt_id, SourceEvidenceDecision.SUFFICIENT, SAFE[:1])
    evaluator = Mock(return_value=gate)
    targets = [(l01, "extract_adapted_receipt_v0"), (s01, "extract_b2_fixture_presentation_v1"),
               (ocr_adapter, "adapt_paddleocr_result"), (baseline_b1, "extract_b1"), (baseline_b3, "apply_b3")]
    with ExitStack() as stack:
        spies = [stack.enter_context(patch.object(module, name, side_effect=AssertionError("Forbidden component.")))
                 for module, name in targets]
        for target in ("builtins.open", "pathlib.Path.open", "os.open", "socket.socket", "subprocess.Popen"):
            stack.enter_context(patch(target, side_effect=AssertionError("External side effect.")))
        result = coordinator.coordinate_synthetic_receipt_v0(
            adapted_source=a, gate_evaluator=evaluator, context=context(), producer_id=PRODUCER,
        )
    validated(result)
    assert all(spy.call_count == 0 for spy in spies)
    evaluator.assert_called_once_with(a)
    assert capsys.readouterr() == ("", "")


def test_public_api_records_and_closed_reason_vocabulary():
    signature = inspect.signature(coordinator.coordinate_synthetic_receipt_v0)
    assert list(signature.parameters) == ["adapted_source", "gate_evaluator", "context", "producer_id", "expected_synthetic_failure"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert signature.parameters["expected_synthetic_failure"].default is None
    assert [item.name for item in Reason] == ["INVALID_INPUT", "INVALID_GATE_RESULT", "ATTACHMENT_REJECTED",
        "INVALID_B2_RESULT", "GATE_EXCEPTION", "B2_EXCEPTION", "PROJECTION_REJECTED", "SYNTHETIC_EVENT_NOT_OBSERVED", "COORDINATOR_FAILED"]
    for record, names in [
        (coordinator.SyntheticExecutionTraceV0, ["adapted_source", "gate_result", "source_evidence", "b2_result"]),
        (coordinator.SyntheticCoordinatorResultV0, ["trace", "result"]),
        (coordinator.SyntheticCoordinatorRejectionV0, ["reason"]),
    ]:
        assert [field.name for field in fields(record)] == names
        assert list(record.__slots__) == names
        assert record.__dataclass_params__.frozen and record.__dataclass_params__.repr is False
    result, _ = exercise()
    with pytest.raises(FrozenInstanceError):
        result.trace.gate_result = None
    imports = [node.module or "" for node in ast.walk(ast.parse(inspect.getsource(coordinator))) if isinstance(node, ast.ImportFrom)]
    assert all(not name.startswith(("tests", "pipeline.proposed", "pipeline.backend_receipt_execution")) for name in imports)
    assert not any(name.startswith("_") for node in ast.walk(ast.parse(inspect.getsource(coordinator)))
                   if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pipeline")
                   for name in [alias.name for alias in node.names])


def test_canonical_fixture_bytes_remain_original():
    root = Path(__file__).resolve().parent / "fixtures/receipt_presentation_v1/v1"
    raw = (root / "manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "4b1bcd3445d82852c7f4c3beb5f0e07f39853497e92713b81a063dcdf5350ee9"
    entries = json.loads(raw)["fixtures"]
    assert len(entries) == len({entry["path"] for entry in entries}) == 32
    for entry in entries:
        content = (root / entry["path"]).read_bytes()
        assert len(content) == entry["byteLength"] and hashlib.sha256(content).hexdigest() == entry["sha256"]
