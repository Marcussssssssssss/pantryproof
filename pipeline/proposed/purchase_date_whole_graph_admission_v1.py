"""Provisional purchase-date cost checks over original synthetic records.

The ready-path numerical model prices only the named operations in its
result. It does not dispatch stages or authorize execution.
"""

from __future__ import annotations

from concurrent.futures import CancelledError as FutureCancelledError
from dataclasses import dataclass, fields
from decimal import Decimal, __libmpdec_version__
from enum import Enum
from math import isfinite
import sys
from sys import maxsize
from types import UnionType
from typing import get_args, get_origin, get_type_hints
from unicodedata import unidata_version

from pipeline import contracts as base
from pipeline.baseline_b3 import B3ParseState
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed import candidate_limiting as limiting
from pipeline.proposed import candidate_ranking as ranking
from pipeline.proposed import contracts as shared
from pipeline.proposed import purchase_date_calendar_validity as calendar
from pipeline.proposed import purchase_date_source_contracts_v1 as d1
from pipeline.proposed import suspicion
from pipeline.proposed.adapter import ProposedAdapterResultV1
from pipeline.proposed.hard_constraint_contracts_v2 import (
    RECORD_VERSION_V2, HardConstraintProfileRefV2, HardConstraintResourceRefV2,
    HardConstraintRuleSpecV2, RuleRequirementV2,
)
from pipeline.proposed.owned_numeric_producer_v1 import (
    OwnedNumericCapacityV1, OwnedNumericErrorCodeV1, OwnedNumericErrorV1,
    OwnedNumericScopeV1,
)


class PreflightStatusV1(str, Enum):
    SUPPORTED_CHECKS_PASSED = "PROSPECTIVE_SUPPORTED_CHECKS_PASSED"
    REFUSED = "PROSPECTIVE_REFUSED"


class PreflightRefusalV1(str, Enum):
    INVALID_LIMITS = "INVALID_LIMITS"
    UNSUPPORTED_RUNTIME = "UNSUPPORTED_RUNTIME"
    INPUT_SHAPE = "INPUT_SHAPE"
    INPUT_LIMIT = "INPUT_LIMIT"
    ACTIVE_CYCLE = "ACTIVE_CYCLE"
    INVALID_UNICODE = "INVALID_UNICODE"
    WRONG_TARGET = "WRONG_TARGET"
    SOURCE_BINDING = "SOURCE_BINDING"
    CONFIGURATION = "CONFIGURATION"
    ARITHMETIC_LIMIT = "ARITHMETIC_LIMIT"
    OWNER_REFUSED = "OWNER_REFUSED"
    ANCHOR_REFUSED = "ANCHOR_REFUSED"
    NUMERIC_VALUE = "NUMERIC_VALUE"
    NUMERIC_CAPACITY = "NUMERIC_CAPACITY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class PreflightCoverageV1(str, Enum):
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    NATIVE_WORKSPACE_NOT_BYTE_ATTESTED = "NATIVE_WORKSPACE_NOT_BYTE_ATTESTED"


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseDatePreflightLimitsV1:
    max_depth: int
    max_occurrences: int
    max_tuple_arity: int
    max_string_width: int
    max_total_text: int
    max_integer_bits: int
    max_tokens: int
    max_polygon_points: int
    max_rows: int
    max_fields: int
    max_seeds: int
    max_spans: int
    max_total_span_length: int
    max_references: int
    max_profile_members: int
    max_census_work: int
    max_arithmetic: int
    max_anchor_count: int
    max_source_id_codepoints: int
    max_total_source_id_codepoints: int
    max_anchor_work: int


@dataclass(frozen=True, slots=True)
class SourceCensusV1:
    occurrences: int
    text_codepoints: int
    work_units: int
    original_tokens: int
    original_fields: int
    original_rows: int
    seed_occurrences: int
    span_occurrences: int
    span_codepoints: int
    reference_occurrences: int
    polygon_point_occurrences: int


@dataclass(frozen=True, slots=True)
class ReadyPathDemandV1:
    possible_proposals: int
    possible_unique_groups: int
    possible_retained: int
    possible_eligible: int
    generation_records: int
    deduplication_b3_calls: int
    g2a_derived_ids: int
    g2a_evidence_references: int
    g2a_operand_validations: int
    g2a_member_validations: int
    regex_passes: int
    regex_attempts: int
    matcher_width: int
    matcher_work: int
    matcher_copy_bytes: int
    matcher_cumulative_scratch_bytes: int
    matcher_peak_scratch_bytes: int
    ranking_derivations: int
    divisions: int
    feature_slot_groups: int
    feature_operand_replays: int
    feature_v2_validations: int


@dataclass(frozen=True, slots=True)
class LogicalCapacityCheckV1:
    dimension: str
    demand: int
    remaining: int


@dataclass(frozen=True, slots=True)
class PurchaseDatePreflightResultV1:
    status: PreflightStatusV1
    refusal: PreflightRefusalV1 | None = None
    census: SourceCensusV1 | None = None
    ready_path: ReadyPathDemandV1 | None = None
    capacity_checks: tuple[LogicalCapacityCheckV1, ...] = ()
    registry_publication_work: int | None = None
    covered_local_lookups: int | None = None
    registry_lookup_work: int | None = None
    anchor_inspection_work: int | None = None
    source_anchors_verified: bool = False
    replay_ledger_totals: tuple[tuple[str, PreflightCoverageV1], ...] = tuple(
        (name, PreflightCoverageV1.NOT_ESTABLISHED)
        for name in ("ID02", "PV01", "R01", "LM01", "FN01-CR01", "HC01", "OP01", "V201", "FR01", "FC01")
    )
    scope_limitations: tuple[tuple[str, PreflightCoverageV1], ...] = (
        ("generation_full_work_and_storage", PreflightCoverageV1.NOT_ESTABLISHED),
        ("deduplication_non_matcher_work_and_storage", PreflightCoverageV1.NOT_ESTABLISHED),
        ("g2a_full_work_and_storage", PreflightCoverageV1.NOT_ESTABLISHED),
        ("downstream_ledger_totals", PreflightCoverageV1.NOT_ESTABLISHED),
        ("blocked_and_other_replay_prefixes", PreflightCoverageV1.NOT_ESTABLISHED),
        ("additional_s01_local_and_foreign_lookups", PreflightCoverageV1.NOT_ESTABLISHED),
        ("upstream_suspicion_decimal_ownership", PreflightCoverageV1.NOT_ESTABLISHED),
        ("outer_decimal_division_workspace", PreflightCoverageV1.NATIVE_WORKSPACE_NOT_BYTE_ATTESTED),
    )
    record_version: str = "purchase-date-prospective-preflight-mvp-v1"


@dataclass(frozen=True, slots=True)
class DateDiscoveryIntakeDemandV1:
    observations: int
    derivations: int
    grouped_proposals: int
    derivation_references: int
    span_occurrences: int
    span_codepoints: int
    possible_d1_drafts: int
    census_work: int
    parser_calls_for_d2_replay: int
    matcher_work_for_d2_replay: int
    hash_calls_for_d2_replay: int
    canonical_bytes_for_d2_replay: int


@dataclass(frozen=True, slots=True)
class DateDiscoveryIntakePreflightV1:
    status: PreflightStatusV1
    refusal: PreflightRefusalV1 | None = None
    discovery_demand: DateDiscoveryIntakeDemandV1 | None = None
    ready_path: ReadyPathDemandV1 | None = None


class _Refuse(Exception):
    pass


_RECORDS = (
    ProposedAdapterResultV1, B2ExtractionResult, base.ReceiptOutput,
    base.ReceiptSourceEvidence, base.SourceEvidenceGateResult, base.SourceProvenance,
    base.OcrSourceToken, base.Point, base.StructuredField, base.ReceiptItemRow,
    base.PreResolutionDisposition, shared.MethodReadyFieldV1, shared.B3CompatibleSeedV1,
    shared.SourceCharacterSpanV1, shared.ConfigurationRefV1, suspicion.SuspicionResultV0,
    suspicion.SuspicionContextV0, suspicion.UpstreamObservationV0,
    suspicion.SuspicionConfigurationV0, suspicion.ConfidenceRuleV0,
    suspicion.ConfidenceObservationV0, suspicion.ConfidenceEvidenceV0,
    ranking.CandidateRankingConfigurationV0, limiting.CandidateLimitingConfigurationV0,
    HardConstraintProfileRefV2, HardConstraintRuleSpecV2, HardConstraintResourceRefV2,
    d1.DateDiscoveryResultV1, d1.DateDiscoveryMethodProfileV1, d1.DateDiscoveryLimitsV1,
    d1.DateOriginalAnchorV1, d1.DateSourceObservationV1, d1.DateDerivationV1,
    d1.DateProposalV1, d1.DateDiscoveryDiagnosticV1,
)
# Resolve only the finite, source-owned layouts above. Input objects and their
# annotations never select attribute accessors or arbitrary container methods.
_SCHEMA = {}
for _record in _RECORDS:
    _hints = get_type_hints(_record)
    _SCHEMA[_record] = tuple((item.name, _hints[item.name]) for item in fields(_record))

_LIMIT_FIELDS = tuple(item.name for item in fields(PurchaseDatePreflightLimitsV1))
_REFERENCE_MEMBERS = frozenset((
    "source_token_ids", "excluded_b2_field_ids", "b3_seed_ids", "b3_event_ids",
    "b3_rule_ids", "evidence_ids", "missing_evidence_ids", "resource_reference_ids",
    "derivation_ids", "interpretations", "token_ids",
))
_POPULATIONS = {
    base.OcrSourceToken: "max_tokens",
    base.Point: "max_polygon_points",
    base.ReceiptItemRow: "max_rows",
    base.StructuredField: "max_fields",
    shared.B3CompatibleSeedV1: "max_seeds",
    shared.SourceCharacterSpanV1: "max_spans",
    HardConstraintRuleSpecV2: "max_profile_members",
    HardConstraintResourceRefV2: "max_profile_members",
}


def _require(condition: bool, code: PreflightRefusalV1) -> None:
    if not condition:
        raise _Refuse(code)


def _checked_add(cap: int, *terms: int) -> int:
    total = 0
    for term in terms:
        if not 0 <= term <= cap - total:
            raise _Refuse(PreflightRefusalV1.ARITHMETIC_LIMIT)
        total += term
    return total


def _checked_mul(cap: int, *factors: int) -> int:
    if 0 in factors:
        return 0
    total = 1
    for factor in factors:
        if not 0 < factor <= cap // total:
            raise _Refuse(PreflightRefusalV1.ARITHMETIC_LIMIT)
        total *= factor
    return total


def _check_limits(limits: PurchaseDatePreflightLimitsV1) -> None:
    _require(type(limits) is PurchaseDatePreflightLimitsV1
             and all(type(value := getattr(limits, name)) is int and 0 < value <= maxsize
                     for name in _LIMIT_FIELDS)
             and limits.max_depth <= 32 and limits.max_integer_bits <= 64,
             PreflightRefusalV1.INVALID_LIMITS)


def _check_runtime() -> None:
    _require(sys.platform == "win32" and maxsize == (1 << 63) - 1
             and sys.version_info[:3] == (3, 13, 7) and ":bcee1c3," in sys.version
             and sys.version.endswith("64 bit (AMD64)]") and sys._is_gil_enabled()
             and unidata_version == "15.1.0" and __libmpdec_version__ == "4.0.0",
             PreflightRefusalV1.UNSUPPORTED_RUNTIME)


class _Census:
    def __init__(self, limits: PurchaseDatePreflightLimitsV1) -> None:
        self.limits = limits
        self.used = dict.fromkeys((
            "max_occurrences", "max_total_text", "max_census_work", "max_references",
            "max_total_span_length", *_POPULATIONS.values(),
        ), 0)
        self.path: list[object] = []

    def charge(self, name: str, amount: int) -> None:
        used = self.used[name]
        _require(amount <= getattr(self.limits, name) - used, PreflightRefusalV1.INPUT_LIMIT)
        self.used[name] = used + amount

    def work(self, amount: int) -> None:
        self.charge("max_census_work", amount)

    def visit(self, value: object, expected: object, member: str = "") -> None:
        depth = len(self.path) + 1
        _require(depth <= self.limits.max_depth, PreflightRefusalV1.INPUT_LIMIT)
        self.charge("max_occurrences", 1)
        self.work(1 + depth)
        if get_origin(expected) is UnionType:
            for option in get_args(expected):
                if type(value) is (get_origin(option) or option) or (
                    option is float and type(value) is int
                ):
                    expected = option
                    break
            else:
                raise _Refuse(PreflightRefusalV1.INPUT_SHAPE)
        kind = type(value)
        _require(kind is (get_origin(expected) or expected) or (
            expected is float and kind is int
        ), PreflightRefusalV1.INPUT_SHAPE)
        if kind is str:
            size = len(value)
            _require(size <= self.limits.max_string_width, PreflightRefusalV1.INPUT_LIMIT)
            self.charge("max_total_text", size)
            self.work(size)
            _require(not any(0xD800 <= ord(char) <= 0xDFFF for char in value),
                     PreflightRefusalV1.INVALID_UNICODE)
        elif kind is int:
            _require(value.bit_length() <= self.limits.max_integer_bits,
                     PreflightRefusalV1.INPUT_LIMIT)
        elif kind is float:
            _require(isfinite(value), PreflightRefusalV1.INPUT_SHAPE)
        elif kind is tuple or kind in _SCHEMA:
            if kind in _POPULATIONS:
                self.charge(_POPULATIONS[kind], 1)
            self._children(value, expected, member)
        elif kind not in (bool, Decimal, type(None)):
            # Enum types are reachable only from the fixed source layouts.
            _require(issubclass(kind, Enum) and any(value is item for item in kind),
                     PreflightRefusalV1.INPUT_SHAPE)

    def _children(self, value: object, expected: object, member: str) -> None:
        if any(value is parent for parent in self.path):
            raise _Refuse(PreflightRefusalV1.ACTIVE_CYCLE)
        kind = type(value)
        is_tuple = kind is tuple
        width = len(value) if is_tuple else len(_SCHEMA[kind])
        if is_tuple:
            _require(width <= self.limits.max_tuple_arity, PreflightRefusalV1.INPUT_LIMIT)
            if member in _REFERENCE_MEMBERS:
                self.charge("max_references", width)
        _require(width <= self.limits.max_occurrences - self.used["max_occurrences"]
                 and (not width or len(self.path) + 1 < self.limits.max_depth),
                 PreflightRefusalV1.INPUT_LIMIT)
        self.work(width)
        self.path.append(value)
        try:
            if is_tuple:
                hints = get_args(expected)
                if len(hints) == 2 and hints[1] is Ellipsis:
                    for child in value:
                        self.visit(child, hints[0])
                else:
                    _require(len(hints) == width, PreflightRefusalV1.INPUT_SHAPE)
                    for child, hint in zip(value, hints, strict=True):
                        self.visit(child, hint)
            else:
                for name, hint in _SCHEMA[kind]:
                    self.visit(getattr(value, name), hint, name)
        finally:
            self.path.pop()
        if kind is shared.SourceCharacterSpanV1:
            length = value.end - value.start
            _require(value.start >= 0 and length > 0 and length == len(value.text),
                     PreflightRefusalV1.SOURCE_BINDING)
            self.charge("max_total_span_length", length)

    def text_equal(self, left: str, right: str) -> bool:
        self.work(1 + len(left) + len(right))
        return left == right

    def same_ids(self, left: tuple[str, ...], right: tuple[str, ...]) -> bool:
        return len(left) == len(right) and all(
            self.text_equal(a, b) for a, b in zip(left, right, strict=True)
        )

    def nonblank(self, value: str) -> bool:
        self.work(1 + len(value))
        return any(not char.isspace() for char in value)

    def unique(self, values: tuple[str, ...]) -> None:
        for index, value in enumerate(values):
            _require(self.nonblank(value), PreflightRefusalV1.SOURCE_BINDING)
            for prior in range(index):
                _require(not self.text_equal(value, values[prior]),
                         PreflightRefusalV1.SOURCE_BINDING)

    def find(self, key: str, records: tuple, member: str) -> object:
        for record in records:
            if self.text_equal(key, getattr(record, member)):
                return record
        raise _Refuse(PreflightRefusalV1.SOURCE_BINDING)


def _check_configuration(census, result, rank, cap, rules, grammar) -> None:
    code = PreflightRefusalV1.CONFIGURATION
    eq = census.text_equal
    theta = result.theta_a_ref
    _require(theta.kind is shared.ConfigurationKind.THETA_A
             and theta.state is shared.ConfigurationState.READY
             and theta.status_reason is None and theta.content_hash is not None
             and census.nonblank(theta.content_hash) and census.nonblank(theta.configuration_id)
             and census.nonblank(theta.configuration_version)
             and eq(theta.record_version, shared.PROPOSED_CONTRACT_VERSION), code)
    for other in (result.configuration.theta_a_ref, rank.theta_a_ref,
                  cap.theta_a_ref, rules.theta_a_reference):
        _require(other.kind is theta.kind and other.state is theta.state
                 and other.status_reason is None and other.content_hash is not None
                 and eq(other.configuration_id, theta.configuration_id)
                 and eq(other.configuration_version, theta.configuration_version)
                 and eq(other.content_hash, theta.content_hash)
                 and eq(other.record_version, shared.PROPOSED_CONTRACT_VERSION), code)
    _require(cap.candidate_limit >= 1 and census.nonblank(cap.fixture_reference)
             and eq(grammar, calendar.PURCHASE_DATE_GRAMMAR_REFERENCE)
             and eq(rank.ranking_profile_id, ranking.CANDIDATE_RANKING_PROFILE_ID)
             and eq(rank.component_version, ranking.CANDIDATE_RANKING_COMPONENT_VERSION)
             and eq(rank.record_version, ranking.CANDIDATE_RANKING_RECORD_VERSION)
             and eq(cap.scope_id, limiting.CANDIDATE_LIMITING_SCOPE_ID)
             and eq(cap.limiting_policy_id, limiting.CANDIDATE_LIMITING_POLICY_ID)
             and eq(cap.tie_policy_id, limiting.CANDIDATE_LIMITING_TIE_POLICY_ID)
             and eq(cap.component_version, limiting.CANDIDATE_LIMITING_COMPONENT_VERSION)
             and eq(cap.record_version, limiting.CANDIDATE_LIMITING_RECORD_VERSION)
             and eq(rules.profile_id, calendar.PURCHASE_DATE_PROFILE_ID)
             and eq(rules.profile_version, calendar.PURCHASE_DATE_PROFILE_VERSION)
             and eq(rules.record_version, RECORD_VERSION_V2)
             and (rules.declared_content_hash is None or census.nonblank(rules.declared_content_hash))
             and not rules.resource_references and len(rules.ordered_rule_specs) == 1, code)
    rule = rules.ordered_rule_specs[0]
    _require(rule.position == 0 and rule.requirement is RuleRequirementV2.MANDATORY
             and not rule.resource_reference_ids and eq(rule.record_version, RECORD_VERSION_V2)
             and eq(rule.rule_id, calendar.PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID)
             and eq(rule.rule_version, calendar.PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION)
             and eq(rule.applicability_reference, calendar.PURCHASE_DATE_APPLICABILITY_REFERENCE),
             code)


def _output_fields(output):
    yield output.store_name
    yield output.purchase_date
    for row in output.items:
        yield row.description
        yield row.quantity
        yield row.unit_price
        yield row.line_total
    yield output.receipt_total


def _original_inputs(census, adapter, result):
    code = PreflightRefusalV1.SOURCE_BINDING
    eq = census.text_equal
    b2 = adapter.original_b2_result
    output = b2.receipt_output
    method = result.method_ready_field
    _require(method.field_name is base.ReceiptFieldName.PURCHASE_DATE,
             PreflightRefusalV1.WRONG_TARGET)
    _require(output is not None and b2.pre_resolution_disposition is None
             and adapter.fallback_disposition is None, code)
    evidence = output.source_evidence
    target = output.purchase_date
    _require(target.field_name is base.ReceiptFieldName.PURCHASE_DATE,
             PreflightRefusalV1.WRONG_TARGET)
    _require(target is method.original_b2_field and target.status is base.FieldStatus.EXTRACTED
             and target.value is not None and census.nonblank(target.value)
             and method.stored_gate_result is evidence.gate_result
             and adapter.stored_gate_result is evidence.gate_result
             and evidence.gate_result.decision is base.SourceEvidenceDecision.SUFFICIENT
             and method.b2_extraction_status is output.extraction_status
             and adapter.b2_extraction_status is output.extraction_status
             and method.source_processing_status is evidence.processing_status
             and eq(method.source_image_id, evidence.image_id)
             and eq(method.b2_extractor_version, output.extractor_version)
             and eq(method.field_id, target.field_id)
             and eq(method.receipt_id, output.receipt_id)
             and eq(adapter.receipt_id, output.receipt_id)
             and eq(evidence.receipt_id, output.receipt_id)
             and eq(evidence.gate_result.receipt_id, output.receipt_id)
             and output.output_stage is base.OutputStage.PRE_REVIEW_AUTOMATIC
             and eq(output.contract_version, base.CONTRACT_VERSION)
             and eq(adapter.record_version, shared.PROPOSED_CONTRACT_VERSION)
             and output.store_name.field_name is base.ReceiptFieldName.STORE_NAME
             and output.receipt_total.field_name is base.ReceiptFieldName.RECEIPT_TOTAL
             and eq(method.original_value, target.value) and eq(method.c0_value, target.value), code)
    context = result.context
    _require(eq(context.receipt_id, method.receipt_id) and eq(context.field_id, method.field_id)
             and eq(context.method_field_id, method.method_field_id)
             and eq(context.gate_result_id, evidence.gate_result.gate_result_id)
             and eq(context.source_image_id, method.source_image_id)
             and census.same_ids(context.source_token_ids, method.source_token_ids), code)

    tokens = evidence.tokens
    field_count = 3 + 4 * len(output.items)
    anchor_count = len(tokens) + field_count
    _require(field_count <= census.limits.max_fields
             and anchor_count <= census.limits.max_anchor_count, PreflightRefusalV1.INPUT_LIMIT)
    census.work(4 * anchor_count + 2 * len(output.items) + len(adapter.method_ready_fields)
                + len(adapter.b3_seeds))
    id_limit = census.limits.max_source_id_codepoints
    _require(all(len(token.token_id) <= id_limit for token in tokens)
             and all(len(field.field_id) <= id_limit for field in _output_fields(output)),
             PreflightRefusalV1.INPUT_LIMIT)
    # Keep the exact order used by the existing B2-to-S01 fixture.
    source_fields = tuple(_output_fields(output))
    census.unique(tuple(token.token_id for token in tokens))
    census.unique(tuple(field.field_id for field in source_fields))
    census.unique(tuple(row.row_id for row in output.items))
    census.unique(tuple(item.field_id for item in adapter.method_ready_fields))
    census.unique(tuple(item.method_field_id for item in adapter.method_ready_fields))
    census.unique(adapter.excluded_b2_field_ids)
    census.unique(tuple(seed.seed_id for seed in adapter.b3_seeds))
    _require(census.find(method.field_id, adapter.method_ready_fields, "field_id") is method, code)
    for token in tokens:
        _require(eq(token.receipt_id, output.receipt_id) and bool(token.original_text)
                 and len(token.polygon) >= 3, code)
    for row in output.items:
        _require(eq(row.receipt_id, output.receipt_id), code)
        for field, role in (
            (row.description, base.ReceiptFieldName.ITEM_DESCRIPTION),
            (row.quantity, base.ReceiptFieldName.QUANTITY),
            (row.unit_price, base.ReceiptFieldName.UNIT_PRICE),
            (row.line_total, base.ReceiptFieldName.LINE_TOTAL),
        ):
            _require(field.field_name is role and field.item_row_id is not None
                     and eq(field.item_row_id, row.row_id), code)
    for field in source_fields:
        _require(eq(field.receipt_id, output.receipt_id), code)
        census.unique(field.source_token_ids)
        for token_id in field.source_token_ids:
            census.find(token_id, tokens, "token_id")
    for item in adapter.method_ready_fields:
        original = census.find(item.field_id, source_fields, "field_id")
        _require(original is item.original_b2_field
                 and original.status is base.FieldStatus.EXTRACTED
                 and original.value is not None and eq(item.original_value, original.value)
                 and eq(item.c0_value, original.value)
                 and item.field_name is original.field_name
                 and item.stored_gate_result is evidence.gate_result
                 and eq(item.receipt_id, output.receipt_id)
                 and eq(item.record_version, shared.PROPOSED_CONTRACT_VERSION)
                 and census.same_ids(item.source_token_ids, original.source_token_ids)
                 and len(item.source_token_ids) == len(item.source_tokens)
                 and not any(eq(item.field_id, excluded) for excluded in adapter.excluded_b2_field_ids),
                 code)
        for token_id, token in zip(item.source_token_ids, item.source_tokens, strict=True):
            _require(census.find(token_id, tokens, "token_id") is token, code)
        census.unique(item.b3_seed_ids)
        for seed_id in item.b3_seed_ids:
            seed = census.find(seed_id, adapter.b3_seeds, "seed_id")
            _require(eq(seed.field_id, item.field_id), code)

    proposals = 0
    literal_width = len(target.value)
    for seed in adapter.b3_seeds:
        bound_field = census.find(seed.field_id, adapter.method_ready_fields, "field_id")
        _require(eq(seed.receipt_id, output.receipt_id)
                 and any(eq(seed.seed_id, identifier) for identifier in bound_field.b3_seed_ids)
                 and eq(seed.c0_candidate_id, bound_field.c0_candidate_id)
                 and eq(seed.c0_value, bound_field.c0_value)
                 and bound_field.b3_ruleset_id is not None
                 and eq(seed.b3_ruleset_id, bound_field.b3_ruleset_id)
                 and seed.source_kind in (shared.CandidateSourceKind.GENERIC_NORMALIZATION,
                                          shared.CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR)
                 and not eq(seed.proposed_value, seed.c0_value)
                 and eq(seed.record_version, shared.PROPOSED_CONTRACT_VERSION)
                 and census.nonblank(seed.proposed_value)
                 and bool(seed.b3_rule_ids) and bool(seed.b3_event_ids),
                 code)
        census.unique(seed.b3_rule_ids)
        census.unique(seed.b3_event_ids)
        for span in seed.source_spans:
            token = census.find(span.token_id, tokens, "token_id")
            _require(span.end <= len(token.original_text), code)
            census.work(span.end - span.start)
            _require(all(token.original_text[index] == char
                         for index, char in enumerate(span.text, span.start)), code)
        if bound_field is method and result.reasons:
            proposals += 1
            literal_width = max(literal_width, len(seed.proposed_value))
    return output, tokens, source_fields, proposals, literal_width


def _ready_path(
    limits: PurchaseDatePreflightLimitsV1, proposals: int, literal_width: int, candidate_limit: int,
) -> ReadyPathDemandV1:
    cap = limits.max_arithmetic
    add, mul = _checked_add, _checked_mul
    # Each targeted seed can produce one proposal. Count even proposals that
    # might collapse into c0 or a shared non-c0 normalization group.
    u = proposals
    n = add(cap, 1, min(u, candidate_limit - 1))
    e = n
    # Public ranking, limiting, finalization and context contribute two
    # derivations apiece. Operand construction plus G2A/FC replays add
    # 10+10n+3e context reconstructions on the successful ready path.
    ranks = add(cap, 18, mul(cap, 10, n), mul(cap, 3, e))
    divisions = mul(cap, 4, u, ranks)
    dedup = add(cap, 4, mul(cap, 16, proposals))
    passes = add(cap, dedup, mul(cap, 2, n))
    # WG02-CR01 pinned NFKC expansion; trimming can only reduce the width.
    width = mul(cap, 18, literal_width)
    return ReadyPathDemandV1(
        possible_proposals=proposals, possible_unique_groups=u, possible_retained=n,
        possible_eligible=e, generation_records=add(cap, 11, mul(cap, 2, proposals)),
        deduplication_b3_calls=dedup, g2a_derived_ids=mul(cap, 2, n),
        g2a_evidence_references=n, g2a_operand_validations=add(cap, 1, mul(cap, 2, n)),
        g2a_member_validations=mul(cap, 2, n), regex_passes=passes,
        regex_attempts=mul(cap, 4, passes), matcher_width=width,
        matcher_work=_matcher_work(cap, passes, width),
        matcher_copy_bytes=mul(cap, passes, add(cap, mul(cap, 1152, width), 288)),
        matcher_cumulative_scratch_bytes=mul(cap, passes, 4680),
        matcher_peak_scratch_bytes=add(cap, 1190),
        ranking_derivations=ranks, divisions=divisions, feature_slot_groups=mul(cap, 5, e),
        feature_operand_replays=add(cap, 7, mul(cap, 3, e), mul(cap, 8, n)),
        feature_v2_validations=add(cap, mul(cap, 2, n), mul(cap, 3, e)),
    )


def _matcher_work(cap: int, passes: int, normalized_width: int) -> int:
    multiply = _checked_mul
    unit = _checked_add(
        cap, 7896, multiply(cap, 33248, normalized_width),
        multiply(cap, 33120, normalized_width, normalized_width),
    )
    return multiply(cap, passes, unit)


def preflight_date_discovery_intake_v1(
    *,
    adapter_result: ProposedAdapterResultV1,
    suspicion_result: suspicion.SuspicionResultV0,
    ranking_configuration: ranking.CandidateRankingConfigurationV0,
    limiting_configuration: limiting.CandidateLimitingConfigurationV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    grammar_reference: str,
    date_discovery: d1.DateDiscoveryResultV1,
    limits: PurchaseDatePreflightLimitsV1,
) -> DateDiscoveryIntakePreflightV1:
    """Check D1 input admission and selected demands without replay or dispatch.

    The ready-path estimate adds potential D1 drafts to the existing B3
    forecast. The replay estimates cover the two direct D2 validations of
    D1, even when a malformed stored result has fewer records than rebuilding
    it would produce. They cover only the named parser and canonical-stream
    dimensions. A pass does not issue whole-graph admission.
    """
    try:
        _check_limits(limits)
        _check_runtime()
        census = _Census(limits)
        for value, expected in (
            (adapter_result, ProposedAdapterResultV1),
            (suspicion_result, suspicion.SuspicionResultV0),
            (ranking_configuration, ranking.CandidateRankingConfigurationV0),
            (limiting_configuration, limiting.CandidateLimitingConfigurationV0),
            (rule_profile_reference, HardConstraintProfileRefV2), (grammar_reference, str),
            (date_discovery, d1.DateDiscoveryResultV1),
        ):
            census.visit(value, expected)
        _check_configuration(census, suspicion_result, ranking_configuration,
                             limiting_configuration, rule_profile_reference, grammar_reference)
        output, tokens, _, b3_count, literal_width = _original_inputs(
            census, adapter_result, suspicion_result,
        )
        demand = _date_discovery_demand(
            census, date_discovery, adapter_result.original_b2_result,
            output, tokens, suspicion_result,
        )
        total = _checked_add(limits.max_arithmetic, b3_count, demand.possible_d1_drafts)
        width = max(literal_width, 10) if demand.possible_d1_drafts else literal_width
        ready = _ready_path(limits, total, width, limiting_configuration.candidate_limit)
        return DateDiscoveryIntakePreflightV1(
            PreflightStatusV1.SUPPORTED_CHECKS_PASSED, discovery_demand=demand, ready_path=ready,
        )
    except _Refuse as exc:
        return DateDiscoveryIntakePreflightV1(PreflightStatusV1.REFUSED, exc.args[0])
    except AttributeError:
        return DateDiscoveryIntakePreflightV1(PreflightStatusV1.REFUSED, PreflightRefusalV1.INPUT_SHAPE)
    except (FutureCancelledError, MemoryError):
        raise
    except Exception:
        return DateDiscoveryIntakePreflightV1(PreflightStatusV1.REFUSED, PreflightRefusalV1.INTERNAL_ERROR)


def _date_discovery_demand(census, discovery, b2_result, output, tokens, result):
    code = PreflightRefusalV1.SOURCE_BINDING
    _require(discovery.b2_result is b2_result and discovery.source_evidence is output.source_evidence
             and discovery.original_anchor.b2_purchase_date_field is output.purchase_date
             and discovery.existing_c0 is None and discovery.original_anchor.existing_c0 is None, code)
    theta = result.theta_a_ref
    for bound in (discovery.theta_a_reference, discovery.method_profile.theta_a_reference):
        _require(bound.kind is theta.kind and bound.state is theta.state
                 and bound.status_reason is None and bound.content_hash is not None
                 and census.text_equal(bound.configuration_id, theta.configuration_id)
                 and census.text_equal(bound.configuration_version, theta.configuration_version)
                 and census.text_equal(bound.content_hash, theta.content_hash)
                 and census.text_equal(bound.record_version, theta.record_version), code)

    count = len(tokens)
    fixed = d1.LIMITS_V1
    _require(count <= fixed.max_source_tokens and count <= census.limits.max_spans // 2
             and discovery.method_profile.limits == fixed, PreflightRefusalV1.INPUT_LIMIT)
    _require(len(discovery.observations) == count and len(discovery.derivations) <= count
             and len(discovery.proposals) <= 2 * count, code)
    census.work(count + len(discovery.proposals))
    span_count = span_chars = source_chars = widest = 0
    for index, token in enumerate(tokens):
        observation = discovery.observations[index]
        _require(observation.source_token is token and observation.token_position == index, code)
        width = len(token.original_text)
        _require(width <= fixed.max_token_codepoints
                 and len(token.polygon) <= fixed.max_polygon_points_per_token,
                 PreflightRefusalV1.INPUT_LIMIT)
        source_chars += width
        widest = max(widest, width)
        for span in (observation.anchor_span, observation.body_span):
            if span is None:
                continue
            _require(census.text_equal(span.token_id, token.token_id) and span.end <= width, code)
            census.work(len(span.text))
            _require(all(token.original_text[i] == char for i, char in enumerate(span.text, span.start)), code)
            span_count += 1
            span_chars += len(span.text)
    _require(source_chars <= census.limits.max_total_span_length, PreflightRefusalV1.INPUT_LIMIT)

    references = proposed = 0
    for proposal in discovery.proposals:
        for reference in proposal.derivation_ids:
            references += 1
            _require(references <= 2 * count, code)
            derivation = census.find(reference, discovery.derivations, "derivation_id")
            observation = census.find(derivation.observation_id, discovery.observations, "observation_id")
            if (derivation.parse_state is B3ParseState.VALID
                    and observation.observation_kind is d1.DateObservationKindV1.ANCHORED_BODY):
                _require(observation.body_span is not None and derivation.normalized_value is not None
                         and census.text_equal(derivation.normalized_value, proposal.normalized_value), code)
                if result.reasons:
                    census.charge("max_seeds", 1)
                    proposed += 1

    cap = census.limits.max_arithmetic
    # Per rebuild: at most one B3 parse and four record IDs per OCR token,
    # plus profile, context, original anchor and result IDs.
    parses = _checked_mul(cap, 2, count)
    hashes = _checked_mul(cap, 2, _checked_add(cap, 4, _checked_mul(cap, 4, count)))
    # Price one streamed hash and up to two full preimage streams per ID.
    streams = _checked_mul(cap, 3, hashes, fixed.max_canonical_bytes)
    normalized_width = _checked_mul(cap, 18, widest)
    return DateDiscoveryIntakeDemandV1(
        len(discovery.observations), len(discovery.derivations), len(discovery.proposals),
        references, span_count, span_chars, proposed, census.used["max_census_work"],
        parses, _matcher_work(cap, parses, normalized_width), hashes, streams,
    )


def _numeric_checks(
    census: _Census, ready: ReadyPathDemandV1, owner_capacity: OwnedNumericCapacityV1,
    method: shared.MethodReadyFieldV1,
) -> tuple[tuple[LogicalCapacityCheckV1, ...], int, int, int]:
    cap = census.limits.max_arithmetic
    add, mul = _checked_add, _checked_mul
    refusal = PreflightRefusalV1.NUMERIC_CAPACITY
    registry = owner_capacity.bounded_registry
    _require(registry is not None, PreflightRefusalV1.OWNER_REFUSED)
    profile = owner_capacity.profile
    native = profile.native_confidence_profile
    divisions = ready.divisions
    bits = profile.max_ratio_int_bits
    digits = (bits + 2) // 3
    if divisions:
        # 10 for the ISO representation, at most three case-folded code points
        # per normalized point for fallback, and unit-width punctuation.
        ratio_width = max(10, mul(cap, 3, ready.matcher_width)).bit_length()
        _require(ratio_width <= bits and max(bits, 34) <= profile.max_coefficient_digits
                 and bits + 33 <= profile.max_exponent_magnitude, refusal)
    recipe_work = mul(cap, divisions, 2 + 2 * digits)
    division_work = mul(cap, divisions, (2 * digits + 34) ** 2)
    groups = ready.feature_slot_groups
    anchor_count = owner_capacity.native_source_anchors.used
    count = retained = native_base_work = source_work = 0
    text_peak = digit_peak = limb_peak = 0
    census.work(len(method.source_tokens) + 1)

    def charge_confidence(value, source_id):
        nonlocal count, retained, native_base_work, source_work, text_peak, digit_peak, limb_peak
        if value is None:
            return
        _require(0 <= value <= 1, PreflightRefusalV1.NUMERIC_VALUE)
        _require(len(source_id) <= profile.max_source_id_codepoints, refusal)
        if type(value) is float:
            envelope, coefficient, limbs, formatter = 24, 17, 0, 25
            _require(native.max_quantum_exponent_magnitude >= 340, refusal)
        else:
            width = value.bit_length()
            envelope = max(1, width + 1)
            coefficient = max(1, (width + 2) // 3)
            cells = (width + 29) // 30
            limbs = 1 + cells + cells // 99
            formatter = 1 + cells * limbs + 2 * cells + limbs + envelope
            _require(width <= native.max_native_int_bits, refusal)
        _require(envelope <= native.max_native_text_chars
                 and coefficient <= native.max_coefficient_digits, refusal)
        count = add(cap, count, groups)
        retained = add(cap, retained, mul(cap, groups, coefficient))
        native_base_work = add(cap, native_base_work, mul(
            cap, groups, add(cap, anchor_count, 6, formatter, 5 * envelope, 2 * coefficient),
        ))
        source_work = add(cap, source_work, mul(cap, groups, 1 + len(source_id)))
        text_peak = max(text_peak, 5 * envelope)
        digit_peak = max(digit_peak, 2 * min(native.max_coefficient_digits, envelope))
        limb_peak = max(limb_peak, limbs)

    for token in method.source_tokens:
        charge_confidence(token.raw_confidence, token.token_id)
    field = method.original_b2_field
    charge_confidence(field.confidence, field.field_id)
    child_work = add(cap, count, retained)
    # Existing native entries increase each conversion's publication scan.
    # Charge every reached attempt as if it saw the largest prospective table.
    native_work = add(cap, native_base_work, mul(
        cap, 4, count, add(cap, owner_capacity.native_registry.used, count),
    ))
    publications = add(cap, mul(cap, 3, divisions), count)
    # Covered lookup sites only: edit-similarity validations within the
    # priced derivations, and the three Decimal-bearing slot roles across
    # five builds and three explicit slot-validation passes per candidate.
    lookups = add(cap, divisions, mul(cap, 24, ready.possible_eligible))
    pub_work = mul(cap, add(cap, registry.process_capacity, 1), publications)
    lookup_work = mul(cap, registry.reserved_slots, lookups)
    owner_work = add(cap, recipe_work, division_work, source_work, lookups, pub_work, lookup_work)
    demands = (
        ("divisions", divisions), ("recipe_constructions", mul(cap, 2, divisions)),
        ("recipe_work", recipe_work), ("owner_registry", publications), ("owner_work", owner_work),
        ("native_attempts", count), ("native_work", native_work), ("native_registry", count),
        ("native_recipe_constructions", count), ("native_recipe_work", child_work),
        ("native_live_text", add(cap, retained, text_peak)),
        ("native_live_digits", add(cap, retained, digit_peak)), ("native_live_limbs", limb_peak),
        ("native_live_binary", 0), ("native_retained_int_bits", 0), ("native_source_anchors", 0),
    )
    checks = tuple(LogicalCapacityCheckV1(name, demand, getattr(owner_capacity, name).remaining)
                   for name, demand in demands)
    return checks, pub_work, lookups, lookup_work


def preflight_purchase_date_whole_graph_v1(
    *,
    adapter_result: ProposedAdapterResultV1,
    suspicion_result: suspicion.SuspicionResultV0,
    ranking_configuration: ranking.CandidateRankingConfigurationV0,
    limiting_configuration: limiting.CandidateLimitingConfigurationV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    grammar_reference: str,
    owner: OwnedNumericScopeV1,
    limits: PurchaseDatePreflightLimitsV1,
) -> PurchaseDatePreflightResultV1:
    """Check the supported prospective dimensions and return a closed diagnostic."""
    try:
        _check_limits(limits)
        _check_runtime()
        _require(type(owner) is OwnedNumericScopeV1, PreflightRefusalV1.OWNER_REFUSED)
        census = _Census(limits)
        for value, expected in (
            (adapter_result, ProposedAdapterResultV1),
            (suspicion_result, suspicion.SuspicionResultV0),
            (ranking_configuration, ranking.CandidateRankingConfigurationV0),
            (limiting_configuration, limiting.CandidateLimitingConfigurationV0),
            (rule_profile_reference, HardConstraintProfileRefV2), (grammar_reference, str),
        ):
            census.visit(value, expected)
        _check_configuration(census, suspicion_result, ranking_configuration,
                             limiting_configuration, rule_profile_reference, grammar_reference)
        output, tokens, source_fields, proposals, literal_width = _original_inputs(
            census, adapter_result, suspicion_result,
        )
        ready = _ready_path(limits, proposals, literal_width, limiting_configuration.candidate_limit)
        count = len(tokens) + len(source_fields)
        cap = limits.max_arithmetic
        width_limit = min(limits.max_source_id_codepoints, maxsize)
        # Clip the product to the explicit text budget before multiplication.
        scan_budget = limits.max_total_source_id_codepoints
        comparison = (scan_budget if count > scan_budget // (2 * width_limit)
                      else 2 * count * width_limit)
        anchor_work = _checked_add(cap, 1, count, comparison)
        try:
            owner.inspect_source_anchor_binding_v1(
                ocr_sources=tokens, extractor_sources=source_fields,
                max_anchor_count=limits.max_anchor_count,
                max_source_id_codepoints=limits.max_source_id_codepoints,
                max_total_source_id_codepoints=scan_budget,
                max_work_units=limits.max_anchor_work,
            )
        except OwnedNumericErrorV1 as exc:
            code = (PreflightRefusalV1.OWNER_REFUSED if exc.code in (
                OwnedNumericErrorCodeV1.FOREIGN_SCOPE, OwnedNumericErrorCodeV1.SCOPE_CLOSED,
                OwnedNumericErrorCodeV1.SCOPE_INVALID,
            ) else PreflightRefusalV1.ANCHOR_REFUSED)
            raise _Refuse(code) from None
        try:
            capacity = owner.inspect_capacity_v1()
        except OwnedNumericErrorV1:
            raise _Refuse(PreflightRefusalV1.OWNER_REFUSED) from None
        checks, pub_work, lookups, lookup_work = _numeric_checks(
            census, ready, capacity, suspicion_result.method_ready_field,
        )
        counts = SourceCensusV1(
            occurrences=census.used["max_occurrences"], text_codepoints=census.used["max_total_text"],
            work_units=census.used["max_census_work"], original_tokens=len(tokens),
            original_fields=len(source_fields), original_rows=len(output.items),
            seed_occurrences=census.used["max_seeds"], span_occurrences=census.used["max_spans"],
            span_codepoints=census.used["max_total_span_length"],
            reference_occurrences=census.used["max_references"],
            polygon_point_occurrences=census.used["max_polygon_points"],
        )
        failed = any(check.demand > check.remaining for check in checks)
        return PurchaseDatePreflightResultV1(
            status=PreflightStatusV1.REFUSED if failed else PreflightStatusV1.SUPPORTED_CHECKS_PASSED,
            refusal=PreflightRefusalV1.NUMERIC_CAPACITY if failed else None,
            census=counts, ready_path=ready, capacity_checks=checks,
            registry_publication_work=pub_work, covered_local_lookups=lookups,
            registry_lookup_work=lookup_work, anchor_inspection_work=anchor_work,
            source_anchors_verified=True,
        )
    except _Refuse as exc:
        return PurchaseDatePreflightResultV1(PreflightStatusV1.REFUSED, exc.args[0])
    except AttributeError:
        # An exact slotted record with uninitialized fields is malformed.
        return PurchaseDatePreflightResultV1(PreflightStatusV1.REFUSED, PreflightRefusalV1.INPUT_SHAPE)
    except (FutureCancelledError, MemoryError):
        # These derive from Exception, unlike asyncio cancellation and interrupts.
        raise
    except Exception:
        # Publish only the closed diagnostic, with no exception text or chain.
        return PurchaseDatePreflightResultV1(PreflightStatusV1.REFUSED, PreflightRefusalV1.INTERNAL_ERROR)
