"""Synthetic conformance for the frozen D0 source-discovery profile."""

import ast
import copy
import inspect
import json
import re
import struct
from dataclasses import FrozenInstanceError, fields, replace
from enum import Enum
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.baseline_b3 import B3ParseState, DateParseResult
from pipeline.contracts import (
    FieldStatus, OcrSourceToken, OutputStage, Point, PolicyState,
    PreResolutionDisposition, ReceiptExtractionStatus, ReceiptFieldName,
    ReceiptItemRow, ReceiptOutput, ReceiptSourceEvidence, SourceEvidenceDecision,
    SourceEvidenceGateResult, SourceProcessingStatus, SourceProvenance, StructuredField,
)
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed import purchase_date_source_contracts_v1 as d1
from pipeline.proposed.contracts import (
    CandidateLimitStatus, CandidateProvenanceV1, CandidateRecordV1, CandidateRole,
    CandidateSourceKind, ConfigurationKind, ConfigurationRefV1, ConfigurationState,
    SourceCharacterSpanV1,
)
from pipeline.proposed.purchase_date_source_discovery_v1 import (
    discover_purchase_date_sources_v1 as discover,
    validate_date_discovery_result_v1 as validate,
)

SCHEMA = "pantryproof-purchase-date-source-discovery-v1"
LIMIT_VECTOR = (500000, 48, 4194304, 512, 64, 2048, 512, 512, 1024, 2048, 16777216)
BUILD = "3.13.7 (tags/v3.13.7:bcee1c3, Aug 14 2025, 14:15:11) [MSC v.1944 64 bit (AMD64)]"
PARSER_HASH = "f417ca5158af5fcb0a0f5757a01e75b708f59a07bc358d93a7eb7ef04c4abb4e"
CONTEXT_KEYS = ("source_evidence", "b2_result", "theta_a_reference", "method_profile", "existing_c0")
PROFILE_DOMAIN = "pantryproof-date-discovery-profile-v1"
CONTEXT_DOMAIN = "pantryproof-date-discovery-context-v1"
Obs, State = d1.DateObservationKindV1, d1.DateOriginalStateV1
Status, Code = d1.DateDiscoveryStatusV1, d1.DateDiscoveryDiagnosticCodeV1
Err = d1.DateDiscoveryErrorCodeV1

# Independently listed schema keys for the canonical oracle. The oracle
# materializes only the small synthetic examples in this file.
ORACLE_FIELDS = {
    Point: "x y",
    SourceProvenance: "source_system source_reference content_sha256",
    OcrSourceToken: "receipt_id token_id original_text polygon raw_confidence",
    SourceEvidenceGateResult: "gate_result_id receipt_id decision reasons",
    ReceiptSourceEvidence: "receipt_id image_id provenance processing_status tokens gate_result",
    StructuredField: (
        "field_id receipt_id field_name status value item_row_id source_token_ids confidence unresolved_reason"
    ),
    ReceiptItemRow: "row_id receipt_id description quantity unit_price line_total pantry_product_identity",
    ReceiptOutput: (
        "receipt_id store_name purchase_date items receipt_total source_evidence extraction_status "
        "extractor_version output_stage contract_version"
    ),
    PreResolutionDisposition: "state gate_result failure_stage failure_reason",
    B2ExtractionResult: "receipt_output pre_resolution_disposition",
    ConfigurationRefV1: "kind configuration_id configuration_version state content_hash status_reason record_version",
    CandidateRecordV1: (
        "candidate_id receipt_id field_id c0_candidate_id value normalized_dedup_key role provenance "
        "limit_status preliminary_rank overflow_reason record_version"
    ),
    CandidateProvenanceV1: (
        "provenance_id receipt_id field_id candidate_id source_kind original_observed_value source_token_ids "
        "source_spans source_order_relationship source_order_position generic_rule_id resource_snapshot_id record_version"
    ),
    SourceCharacterSpanV1: "token_id start end text record_version",
    d1.DateDiscoveryLimitsV1: (
        "max_input_nodes max_input_depth max_input_utf8_bytes max_source_tokens max_polygon_points_per_token "
        "max_token_codepoints max_observations max_derivations max_proposals max_diagnostics max_canonical_bytes"
    ),
    d1.DateDiscoveryMethodProfileV1: (
        "schema_id record_version component_version method_id method_version anchor_grammar_id "
        "anchor_grammar_version encoding_id encoding_version parser_callable parser_ruleset_id parser_source_sha256 "
        "required_b2_extractor_version python_runtime_version unicode_database_version theta_a_reference limits "
        "profile_content_id"
    ),
    d1.DateOriginalAnchorV1: (
        "schema_id record_version anchor_id context_id receipt_id image_id b2_purchase_date_field existing_c0 original_state"
    ),
    d1.DateSourceObservationV1: (
        "schema_id record_version observation_id context_id source_token token_position observation_kind "
        "body_span anchor_span is_b2_date_reference"
    ),
    d1.DateDerivationV1: (
        "schema_id record_version derivation_id context_id observation_id parse_state normalized_value interpretations"
    ),
    d1.DateProposalV1: "schema_id record_version proposal_id context_id normalized_value derivation_ids",
    d1.DateDiscoveryDiagnosticV1: "schema_id record_version code token_ids observation_id",
    d1.DateDiscoveryResultV1: (
        "schema_id record_version result_id context_id source_evidence b2_result theta_a_reference method_profile "
        "existing_c0 original_anchor observations derivations proposals diagnostics status authority_scope"
    ),
}


def _oracle(value, omit=None):
    cls = type(value)
    if isinstance(value, Enum):
        return {"enum_type": cls.__module__ + "." + cls.__name__, "value": value.value}
    if value is None or cls is str:
        return value
    if cls is bool:
        return {"bool": value}
    if cls is int:
        return {"int": str(value)}
    if cls is float:
        return {"binary64": struct.pack(">d", value).hex()}
    if cls is tuple:
        return {"tuple": [_oracle(item) for item in value]}
    return {
        "record_type": cls.__module__ + "." + cls.__name__,
        "fields": {key: _oracle(getattr(value, key)) for key in ORACLE_FIELDS[cls].split() if key != omit},
    }


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _oracle_id(domain, projection):
    return domain + ":sha256:" + sha256(domain.encode("ascii") + b"\x00" + _json_bytes(projection)).hexdigest()


def _profile(theta):
    args = dict(
        component_version="purchase-date-source-discovery-v1",
        method_id="purchase-date-single-token-observation", method_version="1",
        anchor_grammar_id="purchase-date-source-token-anchor", anchor_grammar_version="1",
        encoding_id="pantryproof-date-source-typed-json", encoding_version="1",
        parser_callable="pipeline.baseline_b3.parse_generic_date", parser_ruleset_id="B3-generic-rules-v0",
        parser_source_sha256=PARSER_HASH, required_b2_extractor_version="B2-layout-graph-v0",
        python_runtime_version=BUILD, unicode_database_version="15.1.0",
        theta_a_reference=theta, limits=d1.DateDiscoveryLimitsV1(*LIMIT_VECTOR),
    )
    projected = {"schema_id": SCHEMA, "record_version": "1"}
    projected.update({k: _oracle(v) for k, v in args.items()})
    pid = _oracle_id(PROFILE_DOMAIN, {
        "record_type": "pipeline.proposed.purchase_date_source_contracts_v1.DateDiscoveryMethodProfileV1",
        "fields": projected,
    })
    return d1.DateDiscoveryMethodProfileV1(**args, profile_content_id=pid)


def _forged(record, **changes):
    """Simulate corrupted or reused frozen records without bypassing validation in the API."""
    clone = object.__new__(type(record))
    for f in fields(record):
        object.__setattr__(clone, f.name, changes.get(f.name, getattr(record, f.name)))
    return clone


def _field(name, status=FieldStatus.MISSING, value=None, refs=(), row=None):
    return StructuredField(
        field_id=f"r:b2:{row or 'receipt'}:{name.value}", receipt_id="r", field_name=name,
        status=status, value=value, source_token_ids=refs, item_row_id=row,
        unresolved_reason=None if status is FieldStatus.EXTRACTED else "synthetic evidence unavailable",
    )


def _roots(
    texts=("2026-10-13",), *, state=FieldStatus.MISSING, value=None, refs=None,
    fallback=False, original=False, all_extracted=False, polygon_points=3,
    theta_state=ConfigurationState.NOT_READY,
):
    polygon = (Point(0, -0.0), Point(1.0, 0), Point(0, 1.0)) + (Point(2, 3),) * (polygon_points - 3)
    tokens = tuple(
        OcrSourceToken("r", f"t{i}", text, polygon, (None, 0.0, -0.0)[i % 3])
        for i, text in enumerate(texts)
    )
    gate = SourceEvidenceGateResult(
        "g", "r", SourceEvidenceDecision.INSUFFICIENT if fallback else SourceEvidenceDecision.SUFFICIENT,
        ("synthetic insufficient",) if fallback else (),
    )
    source = ReceiptSourceEvidence(
        "r", "image", SourceProvenance("synthetic", 'line \t\n\r\b\f\x01 "\\ é 😀 /'),
        SourceProcessingStatus.OCR_PARTIAL, tokens, gate,
    )
    theta = ConfigurationRefV1(
        ConfigurationKind.THETA_A, "theta", "1", theta_state,
        content_hash="synthetic" if theta_state is ConfigurationState.READY else None,
        status_reason=None if theta_state is ConfigurationState.READY else "observational only",
    )
    c0 = None
    if fallback:
        b2 = B2ExtractionResult(None, PreResolutionDisposition(PolicyState.FALLBACK_NO_UPDATE, gate))
    else:
        if refs is None:
            refs = (tokens[0].token_id,) if state is FieldStatus.EXTRACTED else ()
        if state is FieldStatus.EXTRACTED and value is None:
            value = tokens[0].original_text
        purchase = _field(ReceiptFieldName.PURCHASE_DATE, state, value, refs)
        store = _field(ReceiptFieldName.STORE_NAME)
        total = _field(ReceiptFieldName.RECEIPT_TOTAL)
        items = ()
        extraction = ReceiptExtractionStatus.PARTIAL if state is FieldStatus.EXTRACTED else ReceiptExtractionStatus.FAILED
        if all_extracted:
            assert state is FieldStatus.EXTRACTED
            store = _field(ReceiptFieldName.STORE_NAME, FieldStatus.EXTRACTED, "Mart", refs)
            total = _field(ReceiptFieldName.RECEIPT_TOTAL, FieldStatus.EXTRACTED, "1.00", refs)
            item_fields = tuple(
                _field(name, FieldStatus.EXTRACTED, "1", refs, row="row")
                for name in (ReceiptFieldName.ITEM_DESCRIPTION, ReceiptFieldName.QUANTITY,
                             ReceiptFieldName.UNIT_PRICE, ReceiptFieldName.LINE_TOTAL)
            )
            items = (ReceiptItemRow("row", "r", *item_fields),)
            extraction = ReceiptExtractionStatus.EXTRACTED
        b2 = B2ExtractionResult(ReceiptOutput("r", store, purchase, items, total, source, extraction, "B2-layout-graph-v0"), None)
        if original:
            cid = purchase.field_id + ":c0"
            prov = CandidateProvenanceV1("p0", "r", purchase.field_id, cid, CandidateSourceKind.ORIGINAL, value, refs)
            c0 = CandidateRecordV1(cid, "r", purchase.field_id, cid, value, value, CandidateRole.ORIGINAL,
                                   (prov,), CandidateLimitStatus.RETAINED)
    return dict(source_evidence=source, b2_result=b2, theta_a_reference=theta,
                method_profile=_profile(theta), existing_c0=c0)


def _swap_source(roots, new):
    roots["source_evidence"] = new
    b2 = roots["b2_result"]
    roots["b2_result"] = _forged(b2, receipt_output=_forged(b2.receipt_output, source_evidence=new))


def _error(code, path=None, limit=None):
    return pytest.raises(d1.DateDiscoveryError, match=f"^{code.value}$",
                         check=lambda e: e.code is code and (path is None or e.path == path)
                         and e.limit_field == limit)


def _dates(result):
    return tuple(p.normalized_value for p in result.proposals)


@pytest.mark.parametrize(("attribute", "replacement"), [
    ("code", Err.CONTENT_ID_MISMATCH),
    ("path", "result"),
    ("limit_field", "max_derivations"),
    ("_code", Err.CONTENT_ID_MISMATCH),
    ("_path", "result"),
    ("_limit_field", "max_derivations"),
])
def test_date_discovery_error_fields_are_immutable(attribute, replacement):
    code = Err.RESOURCE_LIMIT_EXCEEDED
    path = "result.proposals[1024]"
    limit_field = "max_proposals"
    error = d1.DateDiscoveryError(code, path, limit_field)

    with pytest.raises(AttributeError):
        setattr(error, attribute, replacement)
    with pytest.raises(AttributeError):
        delattr(error, attribute)

    assert error.code is code
    assert error.path == path
    assert error.limit_field == limit_field
    assert error.args == ("RESOURCE_LIMIT_EXCEEDED",)
    assert str(error) == "RESOURCE_LIMIT_EXCEEDED"


def test_date_discovery_error_preserves_standard_exception_behavior():
    error = d1.DateDiscoveryError(Err.INPUT_TYPE_INVALID, "source_evidence")
    assert error.limit_field is None

    cause = TypeError("synthetic cause")
    with pytest.raises(ValueError, match="^INPUT_TYPE_INVALID$") as caught:
        try:
            raise cause
        except TypeError as context:
            raise error from context

    assert caught.value is error
    assert error.args == ("INPUT_TYPE_INVALID",)
    assert error.__cause__ is cause
    assert error.__context__ is cause
    assert error.__suppress_context__ is True
    traceback = error.__traceback__
    assert traceback is not None
    error.__traceback__ = None
    assert error.__traceback__ is None
    assert error.with_traceback(traceback) is error
    assert error.__traceback__ is traceback
    error.add_note("synthetic note")
    assert error.__notes__ == ["synthetic note"]


# D1-T01, T02, T04: independent calendar outcomes, including NFKC-only forms.
@pytest.mark.parametrize(("literal", "expected"), [
    ("2026-1-9", ("2026-01-09",)),
    ("13/10/2026", ("2026-10-13",)),
    ("10/13/2026", ("2026-10-13",)),
    (" 13 October 2026 ", ("2026-10-13",)),
    ("October 13, 2026", ("2026-10-13",)),
    ("Ｏｃｔｏｂｅｒ １３， ２０２６", ("2026-10-13",)),
    ("03/04/2026", ("2026-04-03", "2026-03-04")),
    ("10/11/2026", ("2026-11-10", "2026-10-11")),
    ("11/11/2026", ("2026-11-11",)),
    ("02/02/2026", ("2026-02-02",)),
    ("2024-2-29", ("2024-02-29",)),
    ("0001-1-1", ("0001-01-01",)),
    ("9999-12-31", ("9999-12-31",)),
    ("2026-2-29", ()), ("31/02/2026", ()), ("13-10/2026", ()),
    ("00/00/2026", ()), ("11/00/2026", ()), ("0000-1-1", ()),
    ("13/10/26", ()), ("I3/10/2026", ()), ("receipt 2026-10-13", ()),
])
def test_literal_parser_outcomes(literal, expected):
    roots = _roots((literal,))
    result = discover(**roots)
    obs, = result.observations
    derivation, = result.derivations
    assert obs.source_token is roots["source_evidence"].tokens[0]
    assert obs.body_span == SourceCharacterSpanV1("t0", 0, len(literal), literal)
    assert obs.anchor_span is None and obs.observation_kind is Obs.WHOLE_TOKEN
    assert _dates(result) == derivation.interpretations == expected
    assert derivation.observation_id == obs.observation_id
    assert derivation.parse_state is (B3ParseState.INVALID, B3ParseState.VALID, B3ParseState.AMBIGUOUS)[len(expected)]
    assert derivation.normalized_value == (expected[0] if len(expected) == 1 else None)
    assert tuple(x.code for x in result.diagnostics) == {
        0: (Code.NO_METHOD_READY_ORIGINAL, Code.INVALID_OR_UNSUPPORTED_LITERAL, Code.NO_SUPPORTED_DATE_PROPOSALS),
        1: (Code.NO_METHOD_READY_ORIGINAL,),
        2: (Code.NO_METHOD_READY_ORIGINAL, Code.AMBIGUOUS_INTERPRETATIONS_RETAINED),
    }[len(expected)]


# D1-T05: declarative regex used only as the independent synthetic oracle.
NORMATIVE_ANCHOR = re.compile(
    r"^\s*(?:DATE|PURCHASE\s+DATE|TRANSACTION\s+DATE)\b\s*[:#-]?\s*(?P<body>.*?)\s*$",
    re.IGNORECASE,
)


@pytest.mark.parametrize("literal", [
    "DATE: 2026-10-13 ", "\tPurchase\u2003Date # ０３／０４／２０２６",
    "TRANSACTION\nDATE - 2026-10-13\n", "TRANſACTION DATE: 2026-10-13",
    "date", " DATE:\r\n", "PURCHASE DATE#", "DATE:\n 2026-10-13",
    "DATE: 2026-\n10-13", "DATE: 😀2026-10-13", "DATE: x\r2026",
    "EXPIRY DATE: 2026-10-13", "DATE_2026-10-13", "ＤＡＴＥ: 2026-10-13", " \t ",
    "DATE:: 2026-10-13", "DATE/2026-10-13",
])
def test_anchor_matches_declarative_oracle(literal):
    obs, = discover(**_roots((literal,))).observations
    match = NORMATIVE_ANCHOR.fullmatch(literal)
    if match is None:
        assert obs.observation_kind is Obs.WHOLE_TOKEN and obs.anchor_span is None
        assert obs.body_span == SourceCharacterSpanV1("t0", 0, len(literal), literal)
    else:
        start, end = match.span("body")
        assert obs.anchor_span == SourceCharacterSpanV1("t0", 0, start, literal[:start])
        if start == end:
            assert obs.observation_kind is Obs.ANCHOR_ONLY and obs.body_span is None
        else:
            assert obs.observation_kind is Obs.ANCHORED_BODY
            assert obs.body_span == SourceCharacterSpanV1("t0", start, end, literal[start:end])


# D1-T03, T06, T07, T09, T10, T11 and T12: honest routing and retained inputs.
@pytest.mark.parametrize(("options", "expected_state"), [
    ({}, State.MISSING_NO_C0),
    ({"state": FieldStatus.UNRESOLVED}, State.UNRESOLVED_NO_C0),
    ({"state": FieldStatus.EXTRACTED}, State.EXTRACTED_NO_SUPPLIED_C0),
    ({"state": FieldStatus.EXTRACTED, "original": True, "all_extracted": True}, State.EXTRACTED_WITH_SUPPLIED_C0),
    ({"fallback": True}, State.NO_B2_OUTPUT),
])
def test_original_routes_and_reconstruction(options, expected_state):
    roots = _roots(**options)
    result = discover(**roots)
    assert all(getattr(result, k) is roots[k] for k in CONTEXT_KEYS)
    assert result.original_anchor.original_state is expected_state
    assert result.original_anchor.existing_c0 is roots["existing_c0"]
    output = roots["b2_result"].receipt_output
    if output is None:
        assert result.status is Status.NOT_PROCESSABLE_STORED_FALLBACK
        assert result.original_anchor.b2_purchase_date_field is None
        assert not (result.observations or result.derivations or result.proposals)
        assert tuple(x.code for x in result.diagnostics) == (Code.STORED_SOURCE_INSUFFICIENT, Code.NO_METHOD_READY_ORIGINAL)
        assert all(x.observation_id is None and x.token_ids == () for x in result.diagnostics)
        assert result.b2_result.pre_resolution_disposition.gate_result is result.source_evidence.gate_result
    else:
        assert result.original_anchor.b2_purchase_date_field is output.purchase_date
        assert result.status is Status.COMPLETE_WITH_PROPOSALS
        assert _dates(result) == ("2026-10-13",)
    validate(result)
    validate(copy.deepcopy(result))
    assert replace(result) == result
    with pytest.raises(FrozenInstanceError):
        result.status = Status.COMPLETE_NO_PROPOSALS
    assert not hasattr(result, "__dict__")


# D1-T07 through T09 and T15: adversarial source, original and scalar shapes.
@pytest.mark.parametrize(("key", "value", "code", "suffix"), [
    ("token_id", "", Err.INPUT_SHAPE_INVALID, "token_id"),
    ("receipt_id", "other", Err.SOURCE_BINDING_MISMATCH, "receipt_id"),
    ("original_text", "\ud800", Err.INPUT_SHAPE_INVALID, "original_text"),
    ("raw_confidence", float("nan"), Err.INPUT_SHAPE_INVALID, "raw_confidence"),
    ("raw_confidence", float("inf"), Err.INPUT_SHAPE_INVALID, "raw_confidence"),
    ("raw_confidence", True, Err.INPUT_SHAPE_INVALID, "raw_confidence"),
    ("raw_confidence", 2**63, Err.INPUT_SHAPE_INVALID, "raw_confidence"),
    ("polygon", (Point(0, 0), Point(1, 1)), Err.INPUT_SHAPE_INVALID, "polygon"),
    ("polygon", (Point(False, 0), Point(1, 1), Point(1, 0)), Err.INPUT_SHAPE_INVALID, "polygon[0].x"),
    ("polygon", (Point(2**63, 0), Point(1, 1), Point(1, 0)), Err.INPUT_SHAPE_INVALID, "polygon[0].x"),
    ("polygon", (Point(0, float("inf")), Point(1, 1), Point(1, 0)), Err.INPUT_SHAPE_INVALID, "polygon[0].y"),
    ("polygon", ((0, 0), Point(1, 1), Point(1, 0)), Err.INPUT_SHAPE_INVALID, "polygon[0]"),
])
def test_invalid_token_leaves(key, value, code, suffix):
    roots = _roots()
    source = roots["source_evidence"]
    token = _forged(source.tokens[0], **{key: value})
    _swap_source(roots, _forged(source, tokens=(token,)))
    with _error(code, "source_evidence.tokens[0]." + suffix):
        discover(**roots)


def test_source_ref_gate_and_nested_cycle_rejected():
    roots = _roots()
    source = roots["source_evidence"]
    roots["source_evidence"] = replace(source, image_id="other")
    with _error(Err.SOURCE_BINDING_MISMATCH, "b2_result.receipt_output.source_evidence"):
        discover(**roots)
    roots["source_evidence"] = replace(source)
    assert roots["source_evidence"] == source
    with _error(Err.SOURCE_BINDING_MISMATCH, "b2_result.receipt_output.source_evidence"):
        discover(**roots)

    _swap_source(roots, _forged(source, tokens=(source.tokens[0],) * 2))
    with _error(Err.SOURCE_BINDING_MISMATCH, "source_evidence.tokens[1].token_id"):
        discover(**roots)
    _swap_source(roots, _forged(source, gate_result=_forged(source.gate_result, receipt_id="other")))
    with _error(Err.SOURCE_BINDING_MISMATCH, "source_evidence.gate_result.receipt_id"):
        discover(**roots)
    _swap_source(roots, _forged(source, processing_status="OCR_PARTIAL"))
    with _error(Err.INPUT_SHAPE_INVALID, "source_evidence.processing_status"):
        discover(**roots)
    _swap_source(roots, _forged(source, tokens=list(source.tokens)))
    with _error(Err.INPUT_SHAPE_INVALID, "source_evidence.tokens"):
        discover(**roots)

    cycle = _forged(source)
    object.__setattr__(cycle, "tokens", (cycle,))
    _swap_source(roots, cycle)
    with _error(Err.INPUT_SHAPE_INVALID, "source_evidence.tokens[0]"):
        discover(**roots)


def test_fallback_rejects_copied_gate_and_unrelated_original():
    roots = _roots(fallback=True)
    valid_b2 = roots["b2_result"]
    roots["b2_result"] = _forged(valid_b2, pre_resolution_disposition=_forged(
        valid_b2.pre_resolution_disposition, gate_result=replace(roots["source_evidence"].gate_result)
    ))
    with _error(Err.SOURCE_BINDING_MISMATCH, "b2_result.pre_resolution_disposition.gate_result"):
        discover(**roots)
    roots["b2_result"] = valid_b2
    roots["existing_c0"] = _roots(state=FieldStatus.EXTRACTED, original=True)["existing_c0"]
    with _error(Err.ORIGINAL_ASSOCIATION_MISMATCH, "existing_c0"):
        discover(**roots)


@pytest.mark.parametrize(("key", "value", "code"), [
    ("role", CandidateRole.ALTERED, Err.ORIGINAL_ASSOCIATION_MISMATCH),
    ("value", "2026-01-01", Err.ORIGINAL_ASSOCIATION_MISMATCH),
    ("receipt_id", "other", Err.ORIGINAL_ASSOCIATION_MISMATCH),
    ("field_id", "other", Err.ORIGINAL_ASSOCIATION_MISMATCH),
    ("candidate_id", "other", Err.ORIGINAL_ASSOCIATION_MISMATCH),
    ("c0_candidate_id", "other", Err.ORIGINAL_ASSOCIATION_MISMATCH),
    ("overflow_reason", "other", Err.ORIGINAL_ASSOCIATION_MISMATCH),
    ("preliminary_rank", object(), Err.INPUT_SHAPE_INVALID),
])
def test_original_identity_validation(key, value, code):
    roots = _roots(state=FieldStatus.EXTRACTED, original=True)
    roots["existing_c0"] = _forged(roots["existing_c0"], **{key: value})
    with _error(code, "existing_c0." + key):
        discover(**roots)


@pytest.mark.parametrize(("key", "value"), [
    ("source_token_ids", ("other",)), ("source_order_position", 0),
    ("source_order_relationship", "adjacent"), ("generic_rule_id", "other"),
    ("resource_snapshot_id", "other"), ("original_observed_value", "other"),
])
def test_original_provenance_is_source_consistent(key, value):
    roots = _roots(state=FieldStatus.EXTRACTED, original=True)
    c0 = roots["existing_c0"]
    roots["existing_c0"] = _forged(c0, provenance=(_forged(c0.provenance[0], **{key: value}),))
    with _error(Err.ORIGINAL_ASSOCIATION_MISMATCH, "existing_c0.provenance[0]." + key):
        discover(**roots)


@pytest.mark.parametrize(("span_edits", "code", "field"), [
    ({}, None, None), ({"token_id": "other"}, Err.ORIGINAL_ASSOCIATION_MISMATCH, "token_id"),
    ({"start": False}, Err.INPUT_SHAPE_INVALID, "start"),
    ({"start": -1}, Err.ORIGINAL_ASSOCIATION_MISMATCH, "start"),
    ({"end": 11}, Err.ORIGINAL_ASSOCIATION_MISMATCH, "end"),
    ({"text": "2026-10-14"}, Err.ORIGINAL_ASSOCIATION_MISMATCH, "text"),
])
def test_original_span_must_match_existing_token(span_edits, code, field):
    roots = _roots(state=FieldStatus.EXTRACTED, original=True)
    c0 = roots["existing_c0"]
    span = _forged(SourceCharacterSpanV1("t0", 0, 10, "2026-10-13"), **span_edits)
    provenance = c0.provenance[0]
    if code is None:
        provenance = replace(provenance, source_spans=(span,))
    else:
        provenance = _forged(provenance, source_spans=(span,))
    supplied = replace(c0, provenance=(provenance,))
    roots["existing_c0"] = supplied
    if code is None:
        result = discover(**roots)
        assert result.existing_c0 is supplied
        assert result.original_anchor.existing_c0.provenance[0].source_spans[0] is span
    else:
        with _error(code, "existing_c0.provenance[0].source_spans[0]." + field):
            discover(**roots)


@pytest.mark.parametrize("state", [FieldStatus.MISSING, FieldStatus.UNRESOLVED])
def test_original_cannot_be_supplied_for_nonextracted(state):
    roots = _roots(state=state)
    roots["existing_c0"] = _roots(state=FieldStatus.EXTRACTED, original=True)["existing_c0"]
    with _error(Err.ORIGINAL_ASSOCIATION_MISMATCH, "existing_c0"):
        discover(**roots)


def test_invalid_b2_field_links_and_version():
    roots = _roots(state=FieldStatus.EXTRACTED)
    b2 = roots["b2_result"]
    out = b2.receipt_output
    field = out.purchase_date
    for changes, code, suffix in (
        ({"purchase_date": _forged(field, source_token_ids=("other",))},
         Err.SOURCE_BINDING_MISMATCH, "purchase_date.source_token_ids[0]"),
        ({"purchase_date": _forged(field, field_id=out.store_name.field_id)},
         Err.SOURCE_BINDING_MISMATCH, "purchase_date.field_id"),
        ({"extraction_status": ReceiptExtractionStatus.EXTRACTED},
         Err.SOURCE_BINDING_MISMATCH, "extraction_status"),
        ({"output_stage": OutputStage.HUMAN_REVIEWED}, Err.SOURCE_BINDING_MISMATCH, "output_stage"),
        ({"extractor_version": "B2-other"}, Err.PROFILE_UNSUPPORTED, "extractor_version"),
        ({"contract_version": "1"}, Err.PROFILE_UNSUPPORTED, "contract_version"),
    ):
        roots["b2_result"] = _forged(b2, receipt_output=_forged(out, **changes))
        with _error(code, "b2_result.receipt_output." + suffix):
            discover(**roots)


# D1-T13: full-graph boundaries where reachable, isolated guards elsewhere.
@pytest.mark.parametrize("count", [511, 512, 513])
def test_source_token_cap(count):
    roots = _roots(("DATE:",) * count)
    if count == 513:
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, "source_evidence.tokens", "max_source_tokens"):
            discover(**roots)
    else:
        result = discover(**roots)
        assert len(result.observations) == count and not result.derivations


@pytest.mark.parametrize("count", [63, 64, 65])
def test_polygon_cap(count):
    roots = _roots(polygon_points=count)
    if count == 65:
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, "source_evidence.tokens[0].polygon", "max_polygon_points_per_token"):
            discover(**roots)
    else:
        assert len(discover(**roots).observations[0].source_token.polygon) == count


@pytest.mark.parametrize("count", [2047, 2048, 2049])
def test_token_codepoint_cap(count):
    roots = _roots(("😀" * count,))
    if count == 2049:
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, "source_evidence.tokens[0].original_text", "max_token_codepoints"):
            discover(**roots)
    else:
        assert discover(**roots).observations[0].body_span.end == count


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_input_nodes_exact_isolated_boundary(delta):
    budget = d1._InputBudget(d1.LIMITS_V1)
    budget.nodes = 500000 + delta - 1
    if delta == 1:
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, "context", "max_input_nodes"):
            budget.charge_node(0, "context")
    else:
        budget.charge_node(0, "context")
        assert budget.nodes == 500000 + delta


@pytest.mark.parametrize("depth", [47, 48, 49])
def test_depth_exact_isolated_boundary(depth):
    budget = d1._InputBudget(d1.LIMITS_V1)
    if depth == 49:
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, "context", "max_input_depth"):
            budget.charge_node(depth, "context")
    else:
        budget.charge_node(depth, "context")
        assert budget.nodes == 1


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_utf8_exact_isolated_boundary(delta):
    budget = d1._InputBudget(d1.LIMITS_V1)
    budget.utf8_bytes = 4194304 + delta - 4
    if delta == 1:
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, "context", "max_input_utf8_bytes"):
            budget.charge_text("😀", "context")
    else:
        budget.charge_text("😀", "context")
        assert budget.utf8_bytes == 4194304 + delta


def _input_oracle(value, depth):
    if isinstance(value, Enum):
        return 1, len(value.value.encode("utf-8")), depth
    if type(value) is str:
        return 1, len(value.encode("utf-8")), depth
    if type(value) is tuple:
        children = value
    elif type(value) in ORACLE_FIELDS:
        children = [getattr(value, key) for key in ORACLE_FIELDS[type(value)].split()]
    else:
        children = ()
    nested = [_input_oracle(item, depth + 1) for item in children]
    return 1 + sum(n[0] for n in nested), sum(n[1] for n in nested), max([depth] + [n[2] for n in nested])


def test_complete_graph_input_counts_and_duplicate_source_occurrence():
    roots = _roots(("😀é",), state=FieldStatus.EXTRACTED)
    expected = [_input_oracle(roots[k], 1) for k in CONTEXT_KEYS]
    nodes = 1 + sum(v[0] for v in expected)
    utf8 = sum(v[1] for v in expected)
    assert max(v[2] for v in expected) == 8
    source_nodes, source_bytes, _ = _input_oracle(roots["source_evidence"], 1)
    assert source_nodes > 0 and source_bytes > 0
    budget = d1._InputBudget(d1.LIMITS_V1)
    budget.charge_node(0, "context")
    for key, spec in d1._ROOT_SPECS:
        budget.walk(roots[key], spec, key, 1)
    assert (budget.nodes, budget.utf8_bytes) == (nodes, utf8)
    for cap, amount in (("max_input_nodes", nodes), ("max_input_utf8_bytes", utf8), ("max_input_depth", 8)):
        assert d1._checked_context(roots, replace(d1.LIMITS_V1, **{cap: amount}))[0] is roots["b2_result"].receipt_output.purchase_date
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, limit=cap):
            d1._checked_context(roots, replace(d1.LIMITS_V1, **{cap: amount - 1}))


@pytest.mark.parametrize(("collection", "cap"), [
    ("observations", 512), ("derivations", 512), ("proposals", 1024), ("diagnostics", 2048),
])
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_exact_output_append_guard(collection, cap, delta):
    scan = d1._Scan(d1.LIMITS_V1)
    index = cap + delta - 1
    if delta == 1:
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, f"result.{collection}[{index}]", "max_" + collection):
            scan.check_append(collection, index)
    else:
        scan.check_append(collection, index)


@pytest.mark.parametrize("ambiguous_count", [511, 512])
def test_observation_derivation_and_proposal_reachable_maxima(ambiguous_count):
    values = tuple(f"03/04/{year}" for year in range(1000, 1000 + ambiguous_count))
    if ambiguous_count == 511:
        values += ("2026-10-13",)
    result = discover(**_roots(values))
    assert len(result.observations) == len(result.derivations) == 512
    assert len(result.proposals) == 512 + ambiguous_count


def test_reachable_diagnostic_maximum():
    roots = _roots(("not a date",) * 512, state=FieldStatus.EXTRACTED, value="2026-10-13", refs=("t0", "t1"))
    assert len(discover(**roots).diagnostics) == 516


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_canonical_guard_exact_byte_count_with_domain_and_nul(delta):
    domain = "pantryproof-date-discovery-context-v1"
    total = 16777216 + delta
    size = total - len(domain) - 1

    def chunks():
        block = b" " * 4096
        for _ in range(size // len(block)):
            yield block
        yield block[:size % len(block)]

    builder = d1._Identifiers(d1.LIMITS_V1)
    if delta == 1:
        with _error(Err.RESOURCE_LIMIT_EXCEEDED, "result.context_id", "max_canonical_bytes"):
            builder.identify(domain, chunks, "result.context_id")
    else:
        expected = sha256(domain.encode("ascii") + b"\0")
        for part in chunks():
            expected.update(part)
        assert builder.identify(domain, chunks, "result.context_id") == domain + ":sha256:" + expected.hexdigest()
def test_multiple_dates_group_without_using_original_as_preference():
    roots = _roots(
        ("DATE: 03/04/2026", "2026-04-03", "03/04/2026", "2026-10-13"),
        state=FieldStatus.EXTRACTED, value="2026-10-13", refs=("t3", "t0"), original=True,
    )
    result = discover(**roots)
    assert _dates(result) == ("2026-04-03", "2026-03-04", "2026-10-13")
    assert result.original_anchor.existing_c0 is roots["existing_c0"]
    assert result.original_anchor.existing_c0.value == "2026-10-13"
    assert tuple(x.derivation_ids for x in result.proposals) == (
        tuple(result.derivations[i].derivation_id for i in (0, 1, 2)),
        tuple(result.derivations[i].derivation_id for i in (0, 2)),
        (result.derivations[3].derivation_id,),
    )
    assert [o.token_position for o in result.observations] == [0, 1, 2, 3]
    assert [o.is_b2_date_reference for o in result.observations] == [True, False, False, True]
    assert result.diagnostics[0].code is Code.B2_MULTI_TOKEN_CONTEXT_UNCOMPOSED
    assert result.diagnostics[0].token_ids == ("t0", "t3")
    assert discover(**roots) == result
    assert [o.source_token.raw_confidence for o in result.observations[:3]] == [None, 0.0, -0.0]
    assert struct.pack(">d", result.observations[2].source_token.raw_confidence).hex() == "8000000000000000"

    source = roots["source_evidence"]
    _swap_source(roots, replace(source, tokens=tuple(reversed(source.tokens))))
    reordered = discover(**roots)
    assert reordered.context_id != result.context_id
    assert _dates(reordered) == ("2026-10-13", "2026-04-03", "2026-03-04")


def test_unresolved_with_multiple_anchors_and_no_c0():
    roots = _roots(("DATE: 2026-10-13", "PURCHASE DATE: 2026-10-14"),
                   state=FieldStatus.UNRESOLVED, refs=("t1", "t0"))
    result = discover(**roots)
    assert _dates(result) == ("2026-10-13", "2026-10-14")
    assert result.original_anchor.b2_purchase_date_field.value is None
    assert result.original_anchor.b2_purchase_date_field.unresolved_reason == "synthetic evidence unavailable"
    assert result.existing_c0 is None
    assert result.diagnostics[0].token_ids == ("t0", "t1")


def test_separate_regions_are_not_composed_or_linked():
    roots = _roots(("DATE:", "2026-", "10-13", "2026-10-15"),
                   state=FieldStatus.EXTRACTED, value="2026-10-13", refs=("t1", "t2"), original=True)
    result = discover(**roots)
    assert _dates(result) == ("2026-10-15",)
    assert result.observations[0].observation_kind is Obs.ANCHOR_ONLY
    assert result.observations[3].anchor_span is None and not result.observations[3].is_b2_date_reference
    assert len(result.derivations) == 3
    assert result.original_anchor.existing_c0 is roots["existing_c0"]
    assert [d.code for d in result.diagnostics[:2]] == [
        Code.B2_MULTI_TOKEN_CONTEXT_UNCOMPOSED, Code.B2_VALUE_NOT_SINGLE_TOKEN_SOURCE,
    ]


def test_empty_sufficient_source_is_complete_and_fallback_skips_parser(monkeypatch):
    def forbidden(*args):
        pytest.fail("no parser invocation expected")

    monkeypatch.setattr(d1, "parse_generic_date", forbidden)
    result = discover(**_roots(()))
    assert result.status is Status.COMPLETE_NO_PROPOSALS
    assert result.diagnostics[-1].code is Code.NO_SUPPORTED_DATE_PROPOSALS
    validate(result)
    result = discover(**_roots(("DATE: 03/04/2026",), fallback=True))
    assert result.status is Status.NOT_PROCESSABLE_STORED_FALLBACK and not result.proposals
    validate(result)



# D1-T14 and T18: profile/version, complete Theta association and precedence.
@pytest.mark.parametrize(("key", "value", "code"), [
    ("schema_id", "wrong", Err.PROFILE_UNSUPPORTED),
    ("record_version", "2", Err.PROFILE_UNSUPPORTED),
    ("method_version", "2", Err.PROFILE_UNSUPPORTED),
    ("anchor_grammar_id", "wrong", Err.PROFILE_UNSUPPORTED),
    ("encoding_id", "wrong", Err.PROFILE_UNSUPPORTED),
    ("parser_callable", "wrong", Err.PROFILE_UNSUPPORTED),
    ("parser_ruleset_id", "wrong", Err.PROFILE_UNSUPPORTED),
    ("parser_source_sha256", "wrong", Err.PROFILE_UNSUPPORTED),
    ("required_b2_extractor_version", "wrong", Err.PROFILE_UNSUPPORTED),
    ("python_runtime_version", "3.13.7", Err.PROFILE_UNSUPPORTED),
    ("unicode_database_version", "16.0.0", Err.PROFILE_UNSUPPORTED),
    ("profile_content_id", "stale", Err.CONTENT_ID_MISMATCH),
    ("limits", [], Err.INPUT_SHAPE_INVALID),
])
def test_profile_fails_before_parser(key, value, code, monkeypatch):
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: pytest.fail("unexpected parser call"))
    roots = _roots()
    roots["method_profile"] = _forged(roots["method_profile"], **{key: value})
    with _error(code, "method_profile." + key):
        discover(**roots)


@pytest.mark.parametrize("key", ORACLE_FIELDS[d1.DateDiscoveryLimitsV1].split())
def test_no_custom_limit_profile(key, monkeypatch):
    roots = _roots()
    limits = roots["method_profile"].limits
    forged = replace(limits, **{key: getattr(limits, key) - 1})
    roots["method_profile"] = _forged(roots["method_profile"], limits=forged)
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: pytest.fail("unexpected parser call"))
    with _error(Err.PROFILE_UNSUPPORTED, "method_profile.limits." + key):
        discover(**roots)


@pytest.mark.parametrize(("key", "value", "code"), [
    ("configuration_id", "other", Err.THETA_A_ASSOCIATION_MISMATCH),
    ("configuration_version", "2", Err.THETA_A_ASSOCIATION_MISMATCH),
    ("state", ConfigurationState.NOT_VALID, Err.THETA_A_ASSOCIATION_MISMATCH),
    ("content_hash", "some hash", Err.THETA_A_ASSOCIATION_MISMATCH),
    ("status_reason", "another reason", Err.THETA_A_ASSOCIATION_MISMATCH),
    ("kind", ConfigurationKind.KAPPA, Err.INPUT_SHAPE_INVALID),
    ("record_version", "2", Err.PROFILE_UNSUPPORTED),
])
def test_full_theta_reference(key, value, code, monkeypatch):
    roots = _roots()
    roots["theta_a_reference"] = _forged(roots["theta_a_reference"], **{key: value})
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: pytest.fail("unexpected parser call"))
    path = "theta_a_reference"
    if code is not Err.THETA_A_ASSOCIATION_MISMATCH:
        path += "." + key
    with _error(code, path):
        discover(**roots)


@pytest.mark.parametrize("state", [ConfigurationState.NOT_READY, ConfigurationState.NOT_VALID, ConfigurationState.READY])
def test_equal_theta_copy_preserved_without_promotion(state):
    roots = _roots(theta_state=state)
    reference = replace(roots["theta_a_reference"])
    assert reference is not roots["method_profile"].theta_a_reference
    roots["theta_a_reference"] = reference
    result = discover(**roots)
    assert result.theta_a_reference is reference
    assert result.theta_a_reference.state is state


def test_precedence_top_types_profile_then_shape_and_links(monkeypatch):
    roots = _roots(state=FieldStatus.EXTRACTED, original=True)
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: pytest.fail("unexpected parser call"))
    source, profile, theta = roots["source_evidence"], roots["method_profile"], roots["theta_a_reference"]
    roots.update(source_evidence=[], b2_result=[], method_profile=_forged(profile, method_id="wrong"))
    with _error(Err.INPUT_TYPE_INVALID, "source_evidence"):
        discover(**roots)
    roots.update(source_evidence=_forged(source, tokens=[]), b2_result=_roots()["b2_result"])
    with _error(Err.PROFILE_UNSUPPORTED, "method_profile.method_id"):
        discover(**roots)
    roots.update(method_profile=profile)
    with _error(Err.INPUT_SHAPE_INVALID, "source_evidence.tokens"):
        discover(**roots)
    roots = _roots(state=FieldStatus.EXTRACTED, original=True)
    source = roots["source_evidence"]
    roots.update(source_evidence=replace(source), theta_a_reference=replace(theta, configuration_id="other"),
                 existing_c0=_forged(roots["existing_c0"], value="wrong"))
    with _error(Err.SOURCE_BINDING_MISMATCH, "b2_result.receipt_output.source_evidence"):
        discover(**roots)
    roots["source_evidence"] = source
    with _error(Err.THETA_A_ASSOCIATION_MISMATCH, "theta_a_reference"):
        discover(**roots)
    roots["theta_a_reference"] = roots["method_profile"].theta_a_reference
    with _error(Err.ORIGINAL_ASSOCIATION_MISMATCH, "existing_c0.value"):
        discover(**roots)


def test_input_budget_precedes_later_semantic_error(monkeypatch):
    roots = _roots(("DATE:",) * 513)
    roots["theta_a_reference"] = replace(roots["theta_a_reference"], configuration_id="other")
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: pytest.fail("unexpected parser call"))
    with _error(Err.RESOURCE_LIMIT_EXCEEDED, "source_evidence.tokens", "max_source_tokens"):
        discover(**roots)


def test_b2_semantic_checks_follow_field_order(monkeypatch):
    roots = _roots(state=FieldStatus.EXTRACTED)
    b2 = roots["b2_result"]
    output = b2.receipt_output
    roots["b2_result"] = _forged(b2, receipt_output=_forged(
        output, source_evidence=replace(output.source_evidence),
        purchase_date=_forged(output.purchase_date, source_token_ids=("unknown",)),
    ))
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: pytest.fail("unexpected parser call"))
    with _error(Err.SOURCE_BINDING_MISMATCH, "b2_result.receipt_output.purchase_date.source_token_ids[0]"):
        discover(**roots)


def test_runtime_build_pin_is_checked_before_parser(monkeypatch):
    roots = _roots()
    monkeypatch.setattr(d1, "sys", SimpleNamespace(implementation=d1.sys.implementation, version="3.13.7"))
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: pytest.fail("unexpected parser call"))
    with _error(Err.PROFILE_UNSUPPORTED, "method_profile.python_runtime_version"):
        discover(**roots)


def test_real_context_canonical_overflow_is_before_parser(monkeypatch):
    roots = _roots()
    source = roots["source_evidence"]
    _swap_source(roots, replace(source, provenance=replace(source.provenance, source_reference="\x01" * 1400000)))
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: pytest.fail("unexpected parser call"))
    with _error(Err.RESOURCE_LIMIT_EXCEEDED, "result.context_id", "max_canonical_bytes"):
        discover(**roots)


def test_late_canonical_overflow_is_atomic():
    roots = _roots(state=FieldStatus.EXTRACTED, original=True)
    original = replace(roots["existing_c0"], normalized_dedup_key="\x01" * 1500000)
    roots["existing_c0"] = original
    with _error(Err.RESOURCE_LIMIT_EXCEEDED, "result.result_id", "max_canonical_bytes"):
        discover(**roots)
    assert roots["existing_c0"] is original and original.value == "2026-10-13"
    assert roots["source_evidence"] is roots["b2_result"].receipt_output.source_evidence


# D1-T16: independently enumerated exact bytes and all seven domains.
@pytest.mark.parametrize("fallback", [False, True])
def test_all_canonical_preimages_against_independent_oracle(fallback):
    roots = _roots(("DATE: 03/04/2026", "2026-10-13"), state=FieldStatus.EXTRACTED,
                   original=not fallback, fallback=fallback)
    result = discover(**roots)
    context = {name: _oracle(roots[name]) for name in CONTEXT_KEYS}
    assert result.context_id == _oracle_id(CONTEXT_DOMAIN, context)
    assert b"".join(d1._mapping_chunks(iter(sorted(roots.items())))) == _json_bytes(context)
    records = [
        (result.method_profile, "profile_content_id", PROFILE_DOMAIN),
        (result.original_anchor, "anchor_id", "pantryproof-date-original-anchor-v1"),
        (result, "result_id", "pantryproof-date-source-result-v1"),
    ]
    records.extend((x, "observation_id", "pantryproof-date-source-observation-v1") for x in result.observations)
    records.extend((x, "derivation_id", "pantryproof-date-source-derivation-v1") for x in result.derivations)
    records.extend((x, "proposal_id", "pantryproof-date-source-proposal-v1") for x in result.proposals)
    for record, omit, domain in records:
        assert [f.name for f in fields(record)] == ORACLE_FIELDS[type(record)].split()
        projection = _oracle(record, omit)
        assert omit not in projection["fields"]
        assert getattr(record, omit) == _oracle_id(domain, projection)
        assert b"".join(d1._typed_chunks(record, omit)) == _json_bytes(projection)
    result_json = _json_bytes(_oracle(result, "result_id"))
    assert b'"output_stage"' in result_json if not fallback else b'"receipt_output":null' in result_json
    assert b'"existing_c0":null' in result_json if fallback else b'"preliminary_rank":null' in result_json
    assert result.original_anchor.anchor_id.encode() in result_json
    assert result_json.startswith(b"{") and result_json.endswith(b"}")
    assert not result_json.startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize(("value", "expected"), [
    (None, b"null"), (False, b'{"bool":false}'), (0, b'{"int":"0"}'),
    (0.0, b'{"binary64":"0000000000000000"}'), (-0.0, b'{"binary64":"8000000000000000"}'),
    (FieldStatus.EXTRACTED, b'{"enum_type":"pipeline.contracts.FieldStatus","value":"EXTRACTED"}'),
    ("EXTRACTED", b'"EXTRACTED"'), ("a\b\t\n\f\r\x01\"\\é😀/", r'"a\b\t\n\f\r\u0001\"\\é😀/"'.encode("utf-8")),
    ((1, None), b'{"tuple":[{"int":"1"},null]}'),
])
def test_canonical_scalar_and_tuple_bytes(value, expected):
    assert b"".join(d1._typed_chunks(value)) == expected
    assert _json_bytes(_oracle(value)) == expected


def test_native_numeric_changes_bind_context_identity():
    roots = _roots()
    source = roots["source_evidence"]
    base = discover(**roots)
    point = source.tokens[0].polygon[0]
    for new_point in (replace(point, x=0.0), replace(point, y=0.0)):
        token = replace(source.tokens[0], polygon=(new_point, *source.tokens[0].polygon[1:]))
        _swap_source(roots, replace(source, tokens=(token,)))
        other = discover(**roots)
        assert other.context_id == _oracle_id(CONTEXT_DOMAIN, {k: _oracle(roots[k]) for k in CONTEXT_KEYS})
        assert other.context_id != base.context_id
        assert other.observations[0].source_token is token


def test_equal_content_aliases_have_same_id_and_collisions_are_rejected(monkeypatch):
    roots = _roots(("2026-10-13", "2026-10-14"))
    original = discover(**roots)
    assert discover(**copy.deepcopy(roots)).context_id == original.context_id

    class SimulatedHash:
        def __init__(self):
            self.hash = sha256()
            self.force_collision = False

        def update(self, part):
            if part == b"pantryproof-date-source-observation-v1\0":
                self.force_collision = True
            self.hash.update(part)

        def hexdigest(self):
            return "0" * 64 if self.force_collision else self.hash.hexdigest()

    monkeypatch.setattr(d1.hashlib, "sha256", SimulatedHash)
    with _error(Err.CONTENT_ID_COLLISION, "result.observations[1].observation_id"):
        discover(**roots)


# D1-T17: reject forged results even if frozen or value-equal.
def test_reconstruction_detects_forged_results_and_references():
    roots = _roots(("2026-10-13", "13/10/2026"), state=FieldStatus.EXTRACTED, original=True)
    result = discover(**roots)
    o = result.observations[0]
    p = result.proposals[0]
    cases = (
        (dict(observations=result.observations[1:]), Err.SOURCE_BINDING_MISMATCH, "result.observations"),
        (dict(derivations=result.derivations[1:]), Err.SOURCE_BINDING_MISMATCH, "result.derivations"),
        (dict(proposals=result.proposals * 2), Err.SOURCE_BINDING_MISMATCH, "result.proposals"),
        (dict(proposals=(_forged(p, derivation_ids=p.derivation_ids[:1]),)),
         Err.SOURCE_BINDING_MISMATCH, "result.proposals[0].derivation_ids"),
        (dict(proposals=(_forged(p, derivation_ids=p.derivation_ids + ("other",)),)),
         Err.SOURCE_BINDING_MISMATCH, "result.proposals[0].derivation_ids"),
        (dict(observations=tuple(reversed(result.observations))),
         Err.SOURCE_BINDING_MISMATCH, "result.observations[0].source_token"),
        (dict(observations=(_forged(o, source_token=replace(o.source_token)), *result.observations[1:])),
         Err.SOURCE_BINDING_MISMATCH, "result.observations[0].source_token"),
        (dict(observations=(_forged(o, body_span=_forged(o.body_span, start=1)), *result.observations[1:])),
         Err.SOURCE_BINDING_MISMATCH, "result.observations[0].body_span.start"),
        (dict(original_anchor=_forged(result.original_anchor, existing_c0=replace(result.existing_c0))),
         Err.ORIGINAL_ASSOCIATION_MISMATCH, "result.original_anchor.existing_c0"),
        (dict(original_anchor=_forged(result.original_anchor,
                                     b2_purchase_date_field=replace(result.original_anchor.b2_purchase_date_field))),
         Err.SOURCE_BINDING_MISMATCH, "result.original_anchor.b2_purchase_date_field"),
        (dict(status=Status.COMPLETE_NO_PROPOSALS), Err.SOURCE_BINDING_MISMATCH, "result.status"),
        (dict(diagnostics=(d1.DateDiscoveryDiagnosticV1(Code.NO_SUPPORTED_DATE_PROPOSALS, (), None),)),
         Err.SOURCE_BINDING_MISMATCH, "result.diagnostics"),
        (dict(observations=list(result.observations)), Err.INPUT_SHAPE_INVALID, "result.observations"),
        (dict(observations=(True,) * 513), Err.RESOURCE_LIMIT_EXCEEDED, "result.observations[512]"),
        (dict(result_id="stale"), Err.CONTENT_ID_MISMATCH, "result.result_id"),
        (dict(context_id="stale"), Err.CONTENT_ID_MISMATCH, "result.context_id"),
        (dict(method_profile=_forged(result.method_profile, profile_content_id="stale")),
         Err.CONTENT_ID_MISMATCH, "method_profile.profile_content_id"),
    )
    for edits, code, path in cases:
        limit = "max_observations" if code is Err.RESOURCE_LIMIT_EXCEEDED else None
        with _error(code, path, limit):
            validate(_forged(result, **edits))
    with _error(Err.CONTENT_ID_MISMATCH, "result.result_id"):
        replace(result, result_id="stale")
    with _error(Err.CONTENT_ID_MISMATCH, "result.observations[0].observation_id"):
        replace(o, observation_id="stale")
    assert all(getattr(result, k) is roots[k] for k in CONTEXT_KEYS)


@pytest.mark.parametrize("changes", [
    {"original": "wrong"},
    {"state": "VALID"},
    {"normalized_value": None},
    {"interpretations": ("2026-02-31",)},
    {"interpretations": ["2026-10-13"]},
    {"state": B3ParseState.AMBIGUOUS, "normalized_value": None, "interpretations": ("2026-10-13",) * 2},
    {"state": B3ParseState.AMBIGUOUS, "normalized_value": None, "interpretations": ("2026-10-13",) * 3},
    {"state": B3ParseState.INVALID},
])
def test_parser_contract_mismatch(changes, monkeypatch):
    literal = "2026-10-13"
    bad = replace(DateParseResult(literal, B3ParseState.VALID, literal, (literal,)), **changes)
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: bad)
    with _error(Err.PARSER_CONTRACT_MISMATCH, "result.derivations[0]"):
        discover(**_roots((literal,)))


def test_forged_enum_instances_are_rejected_as_shape_failures(monkeypatch):
    roots = _roots()
    source = roots["source_evidence"]
    undeclared_status = str.__new__(SourceProcessingStatus, "OCR_PARTIAL")
    _swap_source(roots, _forged(source, processing_status=undeclared_status))
    with _error(Err.INPUT_SHAPE_INVALID, "source_evidence.processing_status"):
        discover(**roots)

    roots = _roots()
    result = discover(**roots)
    undeclared_result = str.__new__(Status, "COMPLETE_WITH_PROPOSALS")
    with _error(Err.INPUT_SHAPE_INVALID, "result.status"):
        validate(_forged(result, status=undeclared_result))

    undeclared_parse = str.__new__(B3ParseState, "VALID")
    monkeypatch.setattr(d1, "parse_generic_date", lambda s: DateParseResult(s, undeclared_parse, None, (s,)))
    with _error(Err.PARSER_CONTRACT_MISMATCH, "result.derivations[0]"):
        discover(**roots)


def test_parser_exception_is_source_free_and_late_failure_atomic(monkeypatch):
    original_parser = d1.parse_generic_date
    calls = []

    def flaky(literal):
        calls.append(literal)
        if len(calls) == 2:
            raise RuntimeError("private synthetic parser error")
        return original_parser(literal)

    monkeypatch.setattr(d1, "parse_generic_date", flaky)
    roots = _roots(("2026-10-13", "2026-10-14"))
    before = _json_bytes({k: _oracle(roots[k]) for k in CONTEXT_KEYS})
    with _error(Err.PARSER_CONTRACT_MISMATCH, "result.derivations[1]") as caught:
        discover(**roots)
    assert caught.value.__context__ is None
    assert calls == ["2026-10-13", "2026-10-14"]
    assert _json_bytes({k: _oracle(roots[k]) for k in CONTEXT_KEYS}) == before


@pytest.mark.parametrize("exception", [MemoryError, KeyboardInterrupt])
def test_parser_resource_and_process_interruptions_are_preserved(exception, monkeypatch):
    def stop(literal):
        raise exception()

    monkeypatch.setattr(d1, "parse_generic_date", stop)
    with pytest.raises(exception):
        discover(**_roots())


def test_parser_shape_precedes_append_limit_in_isolated_scan(monkeypatch):
    roots = _roots(("2026-10-13", "2026-10-14"))
    tokens = roots["source_evidence"].tokens
    limits = replace(d1.LIMITS_V1, max_derivations=1)
    scan = d1._Scan(limits)
    scan.observe(tokens[0], 0, (Obs.WHOLE_TOKEN, 0, 10), False, "context")
    with monkeypatch.context() as patch:
        patch.setattr(d1, "parse_generic_date", lambda s: object())
        with _error(Err.PARSER_CONTRACT_MISMATCH, "result.derivations[1]"):
            scan.observe(tokens[1], 1, (Obs.WHOLE_TOKEN, 0, 10), False, "context")
    scan = d1._Scan(limits)
    scan.observe(tokens[0], 0, (Obs.WHOLE_TOKEN, 0, 10), False, "context")
    with _error(Err.RESOURCE_LIMIT_EXCEEDED, "result.derivations[1]", "max_derivations"):
        scan.observe(tokens[1], 1, (Obs.WHOLE_TOKEN, 0, 10), False, "context")


# D1-T19: verify imports and call boundaries without running any other pipeline.
def test_direct_api_and_import_boundaries(monkeypatch):
    signature = inspect.signature(discover)
    assert tuple(signature.parameters) == CONTEXT_KEYS
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in signature.parameters.values())
    assert signature.parameters["existing_c0"].default is None
    assert inspect.signature(validate).return_annotation == "None"
    modules = {
        "pipeline.baseline_b3", "pipeline.contracts", "pipeline.layout_b2",
        "pipeline.proposed.contracts", "pipeline.proposed.purchase_date_source_contracts_v1",
    }
    permitted_functions = {"parse_generic_date", "_build_result", "validate_date_discovery_result_v1"}
    for filename in (d1.__file__, inspect.getfile(discover)):
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pipeline"):
                assert node.module in modules
                assert all(alias.name[0].isupper() or alias.name in permitted_functions for alias in node.names)
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("pipeline") for alias in node.names)
    import pipeline.baseline_b3 as b3
    import pipeline.layout_b2 as b2
    import pipeline.ocr_adapter as ocr

    def forbidden(*args, **kwargs):
        pytest.fail("unexpected upstream execution")

    monkeypatch.setattr(b2, "extract_b2", forbidden)
    monkeypatch.setattr(b3, "apply_b3", forbidden)
    monkeypatch.setattr(ocr, "adapt_paddleocr_result", forbidden)
    monkeypatch.setattr(ocr, "attach_gate_result", forbidden)
    result = discover(**_roots())
    assert result.authority_scope == "SOURCE_DISCOVERY_ONLY"
    validate(result)
