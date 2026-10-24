"""Immutable, audit-only hard-constraint Contract V2 records.

This module deliberately does not evaluate hard-rule semantics.  It validates a
complete, ordered audit for one retained candidate and derives the aggregate
state from already-recorded rule outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import json
import re
from typing import Any, Mapping, NoReturn

from pipeline.proposed.contracts import (
    CandidateLimitStatus,
    CandidateProvenanceV1,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    PreliminaryRankV1,
    SourceCharacterSpanV1,
)
from pipeline.proposed.hard_constraint_operands import (
    CandidateOperandAuditV0,
    HardConstraintOperandAuditResultV0,
)


RECORD_VERSION_V2 = "2"
_RULE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class HardConstraintV2Error(ValueError):
    """Base error for Contract V2 validation failures."""


class HardConstraintProfileConfigurationError(HardConstraintV2Error):
    """The declared rule profile is structurally invalid."""


class HardConstraintAuditIntegrityError(HardConstraintV2Error):
    """A candidate audit is incomplete, contradictory, or misbound."""


class HardConstraintSourceBindingError(HardConstraintV2Error):
    """A source-bound factory input is not the exact retained D3 evidence."""


class HardConstraintSerializationError(HardConstraintV2Error):
    """Serialized Contract V2 data is malformed or unsupported."""


class RuleRequirementV2(str, Enum):
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"


class RuleOutcomeStateV2(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"


class RuleEvidenceAvailabilityV2(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ConstraintAggregateStateV2(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    CONSTRAINT_REJECTED = "CONSTRAINT_REJECTED"
    CONSTRAINT_UNAVAILABLE = "CONSTRAINT_UNAVAILABLE"


class ConstraintAggregateReasonV2(str, Enum):
    ALL_APPLICABLE_MANDATORY_RULES_PASSED = (
        "ALL_APPLICABLE_MANDATORY_RULES_PASSED"
    )
    MANDATORY_RULE_FAILED = "MANDATORY_RULE_FAILED"
    MANDATORY_RULE_UNAVAILABLE = "MANDATORY_RULE_UNAVAILABLE"
    NO_APPLICABLE_MANDATORY_RULE = "NO_APPLICABLE_MANDATORY_RULE"


class RuleOutcomeReasonKindV2(str, Enum):
    FAILURE = "FAILURE"
    UNAVAILABILITY = "UNAVAILABILITY"
    PROFILE_EXCLUSION = "PROFILE_EXCLUSION"
    APPROVED_EXCEPTION = "APPROVED_EXCEPTION"


def _fail(error_type: type[HardConstraintV2Error], message: str) -> NoReturn:
    raise error_type(message)


def _require_text(
    value: object,
    name: str,
    error_type: type[HardConstraintV2Error],
) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(error_type, f"{name} must be a nonempty string.")
    return value


def _require_optional_text(
    value: object,
    name: str,
    error_type: type[HardConstraintV2Error],
) -> str | None:
    if value is None:
        return None
    return _require_text(value, name, error_type)


def _require_rule_code(
    value: object,
    name: str,
    error_type: type[HardConstraintV2Error],
) -> str:
    text = _require_text(value, name, error_type)
    if _RULE_CODE_RE.fullmatch(text) is None:
        _fail(error_type, f"{name} must match [A-Z][A-Z0-9_]*.")
    return text


def _require_tuple(
    value: object,
    name: str,
    error_type: type[HardConstraintV2Error],
) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        _fail(error_type, f"{name} must be a tuple.")
    return value


def _require_version(
    value: object,
    error_type: type[HardConstraintV2Error],
) -> None:
    if value != RECORD_VERSION_V2:
        _fail(error_type, f"record_version must be {RECORD_VERSION_V2!r}.")


def _require_enum(
    value: object,
    enum_type: type[Enum],
    name: str,
    error_type: type[HardConstraintV2Error],
) -> None:
    if not isinstance(value, enum_type):
        _fail(error_type, f"{name} must be a {enum_type.__name__} value.")


def _require_exact_integer(
    value: object,
    name: str,
    error_type: type[HardConstraintV2Error],
) -> int:
    if type(value) is not int:
        _fail(error_type, f"{name} must be a non-Boolean integer.")
    return value


def _revalidate_v1(
    value: object,
    expected_type: type[Any],
    name: str,
    error_type: type[HardConstraintV2Error],
) -> None:
    if not isinstance(value, expected_type):
        _fail(error_type, f"{name} must be {expected_type.__name__}.")
    try:
        value.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise error_type(f"{name} is not a valid stored V1 record.") from exc


def _revalidate_candidate_v1(
    value: object,
    name: str,
    error_type: type[HardConstraintV2Error],
) -> None:
    _revalidate_v1(value, CandidateRecordV1, name, error_type)
    candidate = value
    if not isinstance(candidate.role, CandidateRole):
        _fail(error_type, f"{name}.role is not a CandidateRole value.")
    if not isinstance(candidate.limit_status, CandidateLimitStatus):
        _fail(
            error_type,
            f"{name}.limit_status is not a CandidateLimitStatus value.",
        )
    if not isinstance(candidate.provenance, tuple):
        _fail(error_type, f"{name}.provenance must be a tuple.")
    try:
        for provenance in candidate.provenance:
            if not isinstance(provenance, CandidateProvenanceV1):
                _fail(error_type, f"{name}.provenance contains an invalid record.")
            provenance.__post_init__()
            if not isinstance(provenance.source_kind, CandidateSourceKind):
                _fail(
                    error_type,
                    f"{name}.provenance contains an invalid source kind.",
                )
            if provenance.source_order_position is not None:
                _require_exact_integer(
                    provenance.source_order_position,
                    f"{name}.provenance.source_order_position",
                    error_type,
                )
            if not isinstance(provenance.source_spans, tuple):
                _fail(error_type, f"{name}.source_spans must be a tuple.")
            for span in provenance.source_spans:
                if not isinstance(span, SourceCharacterSpanV1):
                    _fail(error_type, f"{name}.source_spans contains an invalid record.")
                span.__post_init__()
                _require_exact_integer(
                    span.start,
                    f"{name}.source_span.start",
                    error_type,
                )
                _require_exact_integer(
                    span.end,
                    f"{name}.source_span.end",
                    error_type,
                )
        if candidate.preliminary_rank is not None:
            if not isinstance(candidate.preliminary_rank, PreliminaryRankV1):
                _fail(error_type, f"{name}.preliminary_rank is invalid.")
            candidate.preliminary_rank.__post_init__()
            for field_name in (
                "source_priority_rank",
                "source_order_displacement",
                "rank_position",
            ):
                _require_exact_integer(
                    getattr(candidate.preliminary_rank, field_name),
                    f"{name}.preliminary_rank.{field_name}",
                    error_type,
                )
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, HardConstraintV2Error):
            raise
        raise error_type(f"{name} nested V1 evidence failed revalidation.") from exc


@dataclass(frozen=True, slots=True)
class HardConstraintResourceRefV2:
    resource_reference_id: str
    resource_kind: str
    resource_id: str
    resource_version: str
    declared_content_reference: str
    declared_content_hash: str | None = None
    record_version: str = RECORD_VERSION_V2

    def __post_init__(self) -> None:
        error = HardConstraintProfileConfigurationError
        _require_version(self.record_version, error)
        _require_text(self.resource_reference_id, "resource_reference_id", error)
        _require_rule_code(self.resource_kind, "resource_kind", error)
        _require_text(self.resource_id, "resource_id", error)
        _require_text(self.resource_version, "resource_version", error)
        _require_text(
            self.declared_content_reference,
            "declared_content_reference",
            error,
        )
        _require_optional_text(
            self.declared_content_hash,
            "declared_content_hash",
            error,
        )


@dataclass(frozen=True, slots=True)
class HardConstraintRuleSpecV2:
    rule_id: str
    rule_version: str
    position: int
    requirement: RuleRequirementV2
    applicability_reference: str
    resource_reference_ids: tuple[str, ...] = ()
    record_version: str = RECORD_VERSION_V2

    def __post_init__(self) -> None:
        error = HardConstraintProfileConfigurationError
        _require_version(self.record_version, error)
        _require_rule_code(self.rule_id, "rule_id", error)
        _require_text(self.rule_version, "rule_version", error)
        if (
            isinstance(self.position, bool)
            or not isinstance(self.position, int)
            or self.position < 0
        ):
            _fail(error, "position must be a non-negative, non-Boolean integer.")
        _require_enum(self.requirement, RuleRequirementV2, "requirement", error)
        _require_text(
            self.applicability_reference,
            "applicability_reference",
            error,
        )
        references = _require_tuple(
            self.resource_reference_ids,
            "resource_reference_ids",
            error,
        )
        for reference_id in references:
            _require_text(reference_id, "resource_reference_id", error)
        if len(set(references)) != len(references):
            _fail(error, "resource_reference_ids must be unique.")


@dataclass(frozen=True, slots=True)
class HardConstraintProfileRefV2:
    profile_id: str
    profile_version: str
    theta_a_reference: ConfigurationRefV1
    ordered_rule_specs: tuple[HardConstraintRuleSpecV2, ...]
    resource_references: tuple[HardConstraintResourceRefV2, ...] = ()
    declared_content_hash: str | None = None
    record_version: str = RECORD_VERSION_V2

    def __post_init__(self) -> None:
        error = HardConstraintProfileConfigurationError
        _require_version(self.record_version, error)
        _require_text(self.profile_id, "profile_id", error)
        _require_text(self.profile_version, "profile_version", error)
        _require_optional_text(
            self.declared_content_hash,
            "declared_content_hash",
            error,
        )
        _revalidate_v1(
            self.theta_a_reference,
            ConfigurationRefV1,
            "theta_a_reference",
            error,
        )
        if self.theta_a_reference.kind is not ConfigurationKind.THETA_A:
            _fail(error, "theta_a_reference must identify THETA_A.")
        if self.theta_a_reference.state is not ConfigurationState.READY:
            _fail(error, "theta_a_reference must be READY.")

        rules = _require_tuple(self.ordered_rule_specs, "ordered_rule_specs", error)
        if not rules:
            _fail(error, "A hard-constraint profile must declare at least one rule.")
        for rule in rules:
            if not isinstance(rule, HardConstraintRuleSpecV2):
                _fail(error, "ordered_rule_specs contains an invalid record.")
            rule.__post_init__()
        if tuple(rule.position for rule in rules) != tuple(range(len(rules))):
            _fail(error, "Rule positions must be contiguous, zero-based, and ordered.")
        rule_ids = tuple(rule.rule_id for rule in rules)
        if len(set(rule_ids)) != len(rule_ids):
            _fail(error, "Rule identifiers must be unique within a profile.")
        if not any(
            rule.requirement is RuleRequirementV2.MANDATORY for rule in rules
        ):
            _fail(error, "A profile must declare at least one mandatory rule.")

        resources = _require_tuple(
            self.resource_references,
            "resource_references",
            error,
        )
        for resource in resources:
            if not isinstance(resource, HardConstraintResourceRefV2):
                _fail(error, "resource_references contains an invalid record.")
            resource.__post_init__()
        resource_ids = tuple(
            resource.resource_reference_id for resource in resources
        )
        if len(set(resource_ids)) != len(resource_ids):
            _fail(error, "Profile resource references must be unique.")
        resource_by_id = dict(zip(resource_ids, resources, strict=True))

        referenced_ids: set[str] = set()
        for rule in rules:
            missing = set(rule.resource_reference_ids).difference(resource_by_id)
            if missing:
                _fail(
                    error,
                    f"Rule {rule.rule_id} references undeclared profile resources.",
                )
            expected_order = tuple(
                resource_id
                for resource_id in resource_ids
                if resource_id in set(rule.resource_reference_ids)
            )
            if rule.resource_reference_ids != expected_order:
                _fail(
                    error,
                    f"Rule {rule.rule_id} resource references must follow profile order.",
                )
            referenced_ids.update(rule.resource_reference_ids)
        if referenced_ids != set(resource_ids):
            _fail(error, "Profile resources must be referenced by at least one rule.")


@dataclass(frozen=True, slots=True)
class EvidenceReferenceV2:
    reference_namespace: str
    reference_id: str
    source_record_version: str | None = None
    record_version: str = RECORD_VERSION_V2

    def __post_init__(self) -> None:
        error = HardConstraintAuditIntegrityError
        _require_version(self.record_version, error)
        _require_rule_code(
            self.reference_namespace,
            "reference_namespace",
            error,
        )
        _require_text(self.reference_id, "reference_id", error)
        _require_optional_text(
            self.source_record_version,
            "source_record_version",
            error,
        )


def _validate_candidate_pair(
    candidate: CandidateRecordV1,
    c0_candidate: CandidateRecordV1,
) -> None:
    error = HardConstraintAuditIntegrityError
    _revalidate_candidate_v1(candidate, "candidate", error)
    _revalidate_candidate_v1(c0_candidate, "c0_candidate", error)
    if c0_candidate.role is not CandidateRole.ORIGINAL:
        _fail(error, "c0_candidate must retain the ORIGINAL role.")
    if c0_candidate.candidate_id != c0_candidate.c0_candidate_id:
        _fail(error, "c0_candidate must be self-referential permanent c0.")
    if c0_candidate.limit_status is not CandidateLimitStatus.RETAINED:
        _fail(error, "c0_candidate must be retained.")
    if candidate.limit_status is not CandidateLimitStatus.RETAINED:
        _fail(error, "Only a retained candidate can receive a V2 audit.")
    if candidate.receipt_id != c0_candidate.receipt_id:
        _fail(error, "candidate and c0_candidate receipt identities differ.")
    if candidate.field_id != c0_candidate.field_id:
        _fail(error, "candidate and c0_candidate field identities differ.")
    if candidate.c0_candidate_id != c0_candidate.candidate_id:
        _fail(error, "candidate is not bound to the supplied permanent c0.")
    if candidate.role is CandidateRole.ORIGINAL and candidate != c0_candidate:
        _fail(error, "An ORIGINAL candidate must equal the supplied permanent c0.")


def _profile_rule(
    profile: HardConstraintProfileRefV2,
    rule_spec: HardConstraintRuleSpecV2,
) -> HardConstraintRuleSpecV2:
    error = HardConstraintAuditIntegrityError
    if rule_spec.position >= len(profile.ordered_rule_specs):
        _fail(error, "rule_spec position is outside the declared profile.")
    expected = profile.ordered_rule_specs[rule_spec.position]
    if rule_spec != expected:
        _fail(error, "rule_spec does not equal the declared profile rule.")
    return expected


@dataclass(frozen=True, slots=True)
class ConstraintRuleOutcomeV2:
    rule_outcome_id: str
    receipt_id: str
    field_id: str
    candidate: CandidateRecordV1
    c0_candidate: CandidateRecordV1
    rule_spec: HardConstraintRuleSpecV2
    state: RuleOutcomeStateV2
    attempted: bool
    evidence_availability: RuleEvidenceAvailabilityV2
    evidence_references: tuple[EvidenceReferenceV2, ...]
    outcome_reason_kind: RuleOutcomeReasonKindV2 | None
    outcome_code: str | None
    outcome_detail: str | None
    theta_a_reference: ConfigurationRefV1
    rule_profile_reference: HardConstraintProfileRefV2
    resource_references: tuple[HardConstraintResourceRefV2, ...] = ()
    record_version: str = RECORD_VERSION_V2

    def __post_init__(self) -> None:
        error = HardConstraintAuditIntegrityError
        _require_version(self.record_version, error)
        _require_text(self.rule_outcome_id, "rule_outcome_id", error)
        _require_text(self.receipt_id, "receipt_id", error)
        _require_text(self.field_id, "field_id", error)
        _validate_candidate_pair(self.candidate, self.c0_candidate)
        if self.receipt_id != self.candidate.receipt_id:
            _fail(error, "receipt_id does not match the audited candidate.")
        if self.field_id != self.candidate.field_id:
            _fail(error, "field_id does not match the audited candidate.")

        if not isinstance(self.rule_profile_reference, HardConstraintProfileRefV2):
            _fail(error, "rule_profile_reference is invalid.")
        self.rule_profile_reference.__post_init__()
        if not isinstance(self.rule_spec, HardConstraintRuleSpecV2):
            _fail(error, "rule_spec is invalid.")
        self.rule_spec.__post_init__()
        _profile_rule(self.rule_profile_reference, self.rule_spec)
        _revalidate_v1(
            self.theta_a_reference,
            ConfigurationRefV1,
            "theta_a_reference",
            error,
        )
        if self.theta_a_reference != self.rule_profile_reference.theta_a_reference:
            _fail(error, "theta_a_reference does not match the rule profile.")

        resources = _require_tuple(
            self.resource_references,
            "resource_references",
            error,
        )
        for resource in resources:
            if not isinstance(resource, HardConstraintResourceRefV2):
                _fail(error, "resource_references contains an invalid record.")
            resource.__post_init__()
        resource_by_id = {
            resource.resource_reference_id: resource
            for resource in self.rule_profile_reference.resource_references
        }
        expected_resources = tuple(
            resource_by_id[reference_id]
            for reference_id in self.rule_spec.resource_reference_ids
        )
        if resources != expected_resources:
            _fail(error, "Rule resources do not match the declared profile resources.")

        _require_enum(self.state, RuleOutcomeStateV2, "state", error)
        if not isinstance(self.attempted, bool):
            _fail(error, "attempted must be Boolean.")
        _require_enum(
            self.evidence_availability,
            RuleEvidenceAvailabilityV2,
            "evidence_availability",
            error,
        )
        evidence = _require_tuple(
            self.evidence_references,
            "evidence_references",
            error,
        )
        for reference in evidence:
            if not isinstance(reference, EvidenceReferenceV2):
                _fail(error, "evidence_references contains an invalid record.")
            reference.__post_init__()
        evidence_keys = tuple(
            (
                reference.reference_namespace,
                reference.reference_id,
                reference.source_record_version,
            )
            for reference in evidence
        )
        if len(set(evidence_keys)) != len(evidence_keys):
            _fail(error, "Evidence references must be unique and ordered.")

        if self.outcome_reason_kind is not None:
            _require_enum(
                self.outcome_reason_kind,
                RuleOutcomeReasonKindV2,
                "outcome_reason_kind",
                error,
            )
        _require_optional_text(self.outcome_detail, "outcome_detail", error)
        if self.outcome_code is not None:
            _require_rule_code(self.outcome_code, "outcome_code", error)

        if self.state is RuleOutcomeStateV2.PASS:
            if not self.attempted:
                _fail(error, "PASS requires attempted=true.")
            if self.evidence_availability is not RuleEvidenceAvailabilityV2.AVAILABLE:
                _fail(error, "PASS requires AVAILABLE evidence status.")
            if any(
                value is not None
                for value in (
                    self.outcome_reason_kind,
                    self.outcome_code,
                    self.outcome_detail,
                )
            ):
                _fail(error, "PASS must not carry reason fields.")
        elif self.state is RuleOutcomeStateV2.FAIL:
            if not self.attempted:
                _fail(error, "FAIL requires attempted=true.")
            if self.evidence_availability is not RuleEvidenceAvailabilityV2.AVAILABLE:
                _fail(error, "FAIL requires AVAILABLE evidence status.")
            if self.outcome_reason_kind is not RuleOutcomeReasonKindV2.FAILURE:
                _fail(error, "FAIL requires a FAILURE reason kind.")
            if self.outcome_code is None:
                _fail(error, "FAIL requires an outcome_code.")
        elif self.state is RuleOutcomeStateV2.NOT_APPLICABLE:
            if self.attempted:
                _fail(error, "NOT_APPLICABLE requires attempted=false.")
            if (
                self.evidence_availability
                is not RuleEvidenceAvailabilityV2.NOT_APPLICABLE
            ):
                _fail(error, "NOT_APPLICABLE requires NOT_APPLICABLE evidence.")
            if self.outcome_reason_kind not in (
                RuleOutcomeReasonKindV2.PROFILE_EXCLUSION,
                RuleOutcomeReasonKindV2.APPROVED_EXCEPTION,
            ):
                _fail(
                    error,
                    "NOT_APPLICABLE requires profile-exclusion or approved-exception provenance.",
                )
            if self.outcome_code is None:
                _fail(error, "NOT_APPLICABLE requires an outcome_code.")
        else:
            if self.evidence_availability is not RuleEvidenceAvailabilityV2.UNAVAILABLE:
                _fail(error, "UNAVAILABLE requires UNAVAILABLE evidence status.")
            if self.outcome_reason_kind is not RuleOutcomeReasonKindV2.UNAVAILABILITY:
                _fail(error, "UNAVAILABLE requires an UNAVAILABILITY reason kind.")
            if self.outcome_code is None:
                _fail(error, "UNAVAILABLE requires an outcome_code.")


def _expected_aggregate(
    profile: HardConstraintProfileRefV2,
    outcomes: tuple[ConstraintRuleOutcomeV2, ...],
) -> tuple[ConstraintAggregateStateV2, ConstraintAggregateReasonV2]:
    mandatory_states = tuple(
        outcome.state
        for rule, outcome in zip(profile.ordered_rule_specs, outcomes, strict=True)
        if rule.requirement is RuleRequirementV2.MANDATORY
    )
    if RuleOutcomeStateV2.FAIL in mandatory_states:
        return (
            ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
            ConstraintAggregateReasonV2.MANDATORY_RULE_FAILED,
        )
    if RuleOutcomeStateV2.UNAVAILABLE in mandatory_states:
        return (
            ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
            ConstraintAggregateReasonV2.MANDATORY_RULE_UNAVAILABLE,
        )
    if RuleOutcomeStateV2.PASS in mandatory_states:
        return (
            ConstraintAggregateStateV2.ELIGIBLE,
            ConstraintAggregateReasonV2.ALL_APPLICABLE_MANDATORY_RULES_PASSED,
        )
    return (
        ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
        ConstraintAggregateReasonV2.NO_APPLICABLE_MANDATORY_RULE,
    )


def _validate_complete_rule_outcomes(
    *,
    profile: HardConstraintProfileRefV2,
    rule_outcomes: object,
    receipt_id: str,
    field_id: str,
    candidate: CandidateRecordV1,
    c0_candidate: CandidateRecordV1,
    theta_a_reference: ConfigurationRefV1,
) -> tuple[ConstraintRuleOutcomeV2, ...]:
    error = HardConstraintAuditIntegrityError
    outcomes = _require_tuple(rule_outcomes, "rule_outcomes", error)
    expected_rules = profile.ordered_rule_specs
    if len(outcomes) != len(expected_rules):
        _fail(
            error,
            "The audit must contain exactly one outcome for every declared rule.",
        )
    outcome_ids: set[str] = set()
    for expected_rule, outcome in zip(expected_rules, outcomes, strict=True):
        if not isinstance(outcome, ConstraintRuleOutcomeV2):
            _fail(error, "rule_outcomes contains an invalid record.")
        outcome.__post_init__()
        if outcome.rule_spec != expected_rule:
            _fail(error, "Rule outcomes must preserve declared profile order.")
        if outcome.rule_outcome_id in outcome_ids:
            _fail(error, "rule_outcome_id values must be unique.")
        outcome_ids.add(outcome.rule_outcome_id)
        if outcome.receipt_id != receipt_id or outcome.field_id != field_id:
            _fail(error, "Rule outcome identity differs from the candidate audit.")
        if outcome.candidate != candidate:
            _fail(error, "Rule outcome is bound to a different candidate record.")
        if outcome.c0_candidate != c0_candidate:
            _fail(error, "Rule outcome is bound to a different permanent c0.")
        if outcome.theta_a_reference != theta_a_reference:
            _fail(error, "Rule outcome Theta_A reference differs from the audit.")
        if outcome.rule_profile_reference != profile:
            _fail(error, "Rule outcome profile differs from the candidate audit.")
    return outcomes


@dataclass(frozen=True, slots=True)
class ConstraintResultV2:
    constraint_result_id: str
    receipt_id: str
    field_id: str
    candidate: CandidateRecordV1
    c0_candidate: CandidateRecordV1
    theta_a_reference: ConfigurationRefV1
    rule_profile_reference: HardConstraintProfileRefV2
    rule_outcomes: tuple[ConstraintRuleOutcomeV2, ...]
    aggregate_state: ConstraintAggregateStateV2
    aggregate_reason: ConstraintAggregateReasonV2
    record_version: str = RECORD_VERSION_V2

    def __post_init__(self) -> None:
        error = HardConstraintAuditIntegrityError
        _require_version(self.record_version, error)
        _require_text(self.constraint_result_id, "constraint_result_id", error)
        _require_text(self.receipt_id, "receipt_id", error)
        _require_text(self.field_id, "field_id", error)
        _validate_candidate_pair(self.candidate, self.c0_candidate)
        if self.receipt_id != self.candidate.receipt_id:
            _fail(error, "receipt_id does not match the audited candidate.")
        if self.field_id != self.candidate.field_id:
            _fail(error, "field_id does not match the audited candidate.")

        if not isinstance(self.rule_profile_reference, HardConstraintProfileRefV2):
            _fail(error, "rule_profile_reference is invalid.")
        self.rule_profile_reference.__post_init__()
        _revalidate_v1(
            self.theta_a_reference,
            ConfigurationRefV1,
            "theta_a_reference",
            error,
        )
        if self.theta_a_reference != self.rule_profile_reference.theta_a_reference:
            _fail(error, "theta_a_reference does not match the rule profile.")

        outcomes = _validate_complete_rule_outcomes(
            profile=self.rule_profile_reference,
            rule_outcomes=self.rule_outcomes,
            receipt_id=self.receipt_id,
            field_id=self.field_id,
            candidate=self.candidate,
            c0_candidate=self.c0_candidate,
            theta_a_reference=self.theta_a_reference,
        )

        _require_enum(
            self.aggregate_state,
            ConstraintAggregateStateV2,
            "aggregate_state",
            error,
        )
        _require_enum(
            self.aggregate_reason,
            ConstraintAggregateReasonV2,
            "aggregate_reason",
            error,
        )
        expected_state, expected_reason = _expected_aggregate(
            self.rule_profile_reference,
            outcomes,
        )
        if (self.aggregate_state, self.aggregate_reason) != (
            expected_state,
            expected_reason,
        ):
            _fail(error, "Aggregate state/reason contradicts the mandatory rule outcomes.")


def build_source_bound_constraint_result_v2(
    *,
    constraint_result_id: str,
    operand_audit: HardConstraintOperandAuditResultV0,
    candidate_audit: CandidateOperandAuditV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    rule_outcomes: tuple[ConstraintRuleOutcomeV2, ...],
) -> ConstraintResultV2:
    """Build one V2 audit while checking exact retained D3 object references.

    This factory verifies source-object identity only at the live D3 boundary.  A
    standalone or deserialized ``ConstraintResultV2`` can preserve immutable
    content equality, but cannot independently recover Python object identity.
    """

    error = HardConstraintSourceBindingError
    if not isinstance(operand_audit, HardConstraintOperandAuditResultV0):
        _fail(error, "operand_audit must be HardConstraintOperandAuditResultV0.")
    if not isinstance(candidate_audit, CandidateOperandAuditV0):
        _fail(error, "candidate_audit must be CandidateOperandAuditV0.")
    if not isinstance(rule_profile_reference, HardConstraintProfileRefV2):
        _fail(error, "rule_profile_reference must be HardConstraintProfileRefV2.")
    try:
        operand_audit.__post_init__()
        candidate_audit.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise error("Source-bound factory inputs failed upstream validation.") from exc
    rule_profile_reference.__post_init__()
    upstream_theta_a = operand_audit.hard_constraint_input.theta_a_ref
    if rule_profile_reference.theta_a_reference != upstream_theta_a:
        _fail(
            error,
            "The V2 profile Theta_A reference differs from the live D3 context.",
        )

    exact_audit = next(
        (
            stored
            for stored in operand_audit.candidate_audits
            if stored is candidate_audit
        ),
        None,
    )
    if exact_audit is None:
        _fail(error, "candidate_audit is not the exact D3 aggregate member.")

    retained = operand_audit.hard_constraint_input.candidates
    if not retained:
        _fail(error, "The D3 context has no retained candidates.")
    c0_candidate = retained[0]
    candidate = candidate_audit.candidate
    if not any(stored is candidate for stored in retained):
        _fail(error, "candidate is not an exact retained D3 candidate reference.")

    outcomes = _validate_complete_rule_outcomes(
        profile=rule_profile_reference,
        rule_outcomes=rule_outcomes,
        receipt_id=candidate.receipt_id,
        field_id=candidate.field_id,
        candidate=candidate,
        c0_candidate=c0_candidate,
        theta_a_reference=rule_profile_reference.theta_a_reference,
    )
    for outcome in outcomes:
        if outcome.candidate is not candidate:
            _fail(error, "Rule outcome candidate is not the exact D3 candidate.")
        if outcome.c0_candidate is not c0_candidate:
            _fail(error, "Rule outcome c0 is not the exact D3 permanent c0.")

    state, reason = _expected_aggregate(rule_profile_reference, outcomes)
    return ConstraintResultV2(
        constraint_result_id=constraint_result_id,
        receipt_id=candidate.receipt_id,
        field_id=candidate.field_id,
        candidate=candidate,
        c0_candidate=c0_candidate,
        theta_a_reference=rule_profile_reference.theta_a_reference,
        rule_profile_reference=rule_profile_reference,
        rule_outcomes=outcomes,
        aggregate_state=state,
        aggregate_reason=reason,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
            if field.init and not field.name.startswith("_")
        }
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise HardConstraintSerializationError(
        f"Unsupported serialization value: {type(value).__name__}."
    )


def constraint_result_v2_to_json(result: ConstraintResultV2) -> str:
    if not isinstance(result, ConstraintResultV2):
        raise HardConstraintSerializationError(
            "result must be a ConstraintResultV2 record."
        )
    result.__post_init__()
    try:
        return json.dumps(
            _json_value(result),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise HardConstraintSerializationError(
            "ConstraintResultV2 serialization failed."
        ) from exc


def _object(value: Any, expected: tuple[str, ...], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HardConstraintSerializationError(f"{name} must be a JSON object.")
    actual = set(value)
    wanted = set(expected)
    if actual != wanted:
        missing = sorted(wanted - actual)
        extra = sorted(actual - wanted)
        raise HardConstraintSerializationError(
            f"{name} fields differ; missing={missing}, extra={extra}."
        )
    return value


def _array(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise HardConstraintSerializationError(f"{name} must be a JSON array.")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise HardConstraintSerializationError(f"{name} must be a JSON string.")
    return value


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HardConstraintSerializationError(
            f"{name} must be a non-Boolean JSON integer."
        )
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise HardConstraintSerializationError(f"{name} must be Boolean.")
    return value


def _enum(value: Any, enum_type: type[Enum], name: str) -> Any:
    text = _string(value, name)
    try:
        return enum_type(text)
    except ValueError as exc:
        raise HardConstraintSerializationError(
            f"{name} contains an unknown {enum_type.__name__} value."
        ) from exc


def _decimal(value: Any, name: str) -> Decimal:
    text = _string(value, name)
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise HardConstraintSerializationError(f"{name} is not a Decimal string.") from exc
    if not number.is_finite():
        raise HardConstraintSerializationError(f"{name} must be finite.")
    return number


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HardConstraintSerializationError(
                f"Duplicate JSON object key is not permitted: {key!r}."
            )
        result[key] = value
    return result


def _configuration(value: Any) -> ConfigurationRefV1:
    data = _object(
        value,
        (
            "kind",
            "configuration_id",
            "configuration_version",
            "state",
            "content_hash",
            "status_reason",
            "record_version",
        ),
        "ConfigurationRefV1",
    )
    return ConfigurationRefV1(
        kind=_enum(data["kind"], ConfigurationKind, "kind"),
        configuration_id=_string(data["configuration_id"], "configuration_id"),
        configuration_version=_string(
            data["configuration_version"], "configuration_version"
        ),
        state=_enum(data["state"], ConfigurationState, "state"),
        content_hash=_optional_string(data["content_hash"], "content_hash"),
        status_reason=_optional_string(data["status_reason"], "status_reason"),
        record_version=_string(data["record_version"], "record_version"),
    )


def _source_span(value: Any) -> SourceCharacterSpanV1:
    data = _object(
        value,
        ("token_id", "start", "end", "text", "record_version"),
        "SourceCharacterSpanV1",
    )
    return SourceCharacterSpanV1(
        token_id=_string(data["token_id"], "token_id"),
        start=_integer(data["start"], "start"),
        end=_integer(data["end"], "end"),
        text=_string(data["text"], "text"),
        record_version=_string(data["record_version"], "record_version"),
    )


def _provenance(value: Any) -> CandidateProvenanceV1:
    data = _object(
        value,
        (
            "provenance_id",
            "receipt_id",
            "field_id",
            "candidate_id",
            "source_kind",
            "original_observed_value",
            "source_token_ids",
            "source_spans",
            "source_order_relationship",
            "source_order_position",
            "generic_rule_id",
            "resource_snapshot_id",
            "record_version",
        ),
        "CandidateProvenanceV1",
    )
    position = data["source_order_position"]
    return CandidateProvenanceV1(
        provenance_id=_string(data["provenance_id"], "provenance_id"),
        receipt_id=_string(data["receipt_id"], "receipt_id"),
        field_id=_string(data["field_id"], "field_id"),
        candidate_id=_string(data["candidate_id"], "candidate_id"),
        source_kind=_enum(data["source_kind"], CandidateSourceKind, "source_kind"),
        original_observed_value=_string(
            data["original_observed_value"], "original_observed_value"
        ),
        source_token_ids=tuple(
            _string(item, "source_token_id")
            for item in _array(data["source_token_ids"], "source_token_ids")
        ),
        source_spans=tuple(
            _source_span(item)
            for item in _array(data["source_spans"], "source_spans")
        ),
        source_order_relationship=_optional_string(
            data["source_order_relationship"], "source_order_relationship"
        ),
        source_order_position=(
            None if position is None else _integer(position, "source_order_position")
        ),
        generic_rule_id=_optional_string(data["generic_rule_id"], "generic_rule_id"),
        resource_snapshot_id=_optional_string(
            data["resource_snapshot_id"], "resource_snapshot_id"
        ),
        record_version=_string(data["record_version"], "record_version"),
    )


def _rank(value: Any) -> PreliminaryRankV1:
    data = _object(
        value,
        (
            "source_priority_rank",
            "normalized_edit_similarity",
            "source_order_displacement",
            "normalized_candidate_text",
            "rank_position",
            "tie_group_id",
            "record_version",
        ),
        "PreliminaryRankV1",
    )
    return PreliminaryRankV1(
        source_priority_rank=_integer(
            data["source_priority_rank"], "source_priority_rank"
        ),
        normalized_edit_similarity=_decimal(
            data["normalized_edit_similarity"], "normalized_edit_similarity"
        ),
        source_order_displacement=_integer(
            data["source_order_displacement"], "source_order_displacement"
        ),
        normalized_candidate_text=_string(
            data["normalized_candidate_text"], "normalized_candidate_text"
        ),
        rank_position=_integer(data["rank_position"], "rank_position"),
        tie_group_id=_string(data["tie_group_id"], "tie_group_id"),
        record_version=_string(data["record_version"], "record_version"),
    )


def _candidate(value: Any) -> CandidateRecordV1:
    data = _object(
        value,
        (
            "candidate_id",
            "receipt_id",
            "field_id",
            "c0_candidate_id",
            "value",
            "normalized_dedup_key",
            "role",
            "provenance",
            "limit_status",
            "preliminary_rank",
            "overflow_reason",
            "record_version",
        ),
        "CandidateRecordV1",
    )
    rank = data["preliminary_rank"]
    return CandidateRecordV1(
        candidate_id=_string(data["candidate_id"], "candidate_id"),
        receipt_id=_string(data["receipt_id"], "receipt_id"),
        field_id=_string(data["field_id"], "field_id"),
        c0_candidate_id=_string(data["c0_candidate_id"], "c0_candidate_id"),
        value=_string(data["value"], "value"),
        normalized_dedup_key=_string(
            data["normalized_dedup_key"], "normalized_dedup_key"
        ),
        role=_enum(data["role"], CandidateRole, "role"),
        provenance=tuple(
            _provenance(item)
            for item in _array(data["provenance"], "provenance")
        ),
        limit_status=_enum(
            data["limit_status"], CandidateLimitStatus, "limit_status"
        ),
        preliminary_rank=None if rank is None else _rank(rank),
        overflow_reason=_optional_string(data["overflow_reason"], "overflow_reason"),
        record_version=_string(data["record_version"], "record_version"),
    )


def _resource(value: Any) -> HardConstraintResourceRefV2:
    data = _object(
        value,
        (
            "resource_reference_id",
            "resource_kind",
            "resource_id",
            "resource_version",
            "declared_content_reference",
            "declared_content_hash",
            "record_version",
        ),
        "HardConstraintResourceRefV2",
    )
    return HardConstraintResourceRefV2(
        resource_reference_id=_string(
            data["resource_reference_id"], "resource_reference_id"
        ),
        resource_kind=_string(data["resource_kind"], "resource_kind"),
        resource_id=_string(data["resource_id"], "resource_id"),
        resource_version=_string(data["resource_version"], "resource_version"),
        declared_content_reference=_string(
            data["declared_content_reference"], "declared_content_reference"
        ),
        declared_content_hash=_optional_string(
            data["declared_content_hash"], "declared_content_hash"
        ),
        record_version=_string(data["record_version"], "record_version"),
    )


def _rule_spec(value: Any) -> HardConstraintRuleSpecV2:
    data = _object(
        value,
        (
            "rule_id",
            "rule_version",
            "position",
            "requirement",
            "applicability_reference",
            "resource_reference_ids",
            "record_version",
        ),
        "HardConstraintRuleSpecV2",
    )
    return HardConstraintRuleSpecV2(
        rule_id=_string(data["rule_id"], "rule_id"),
        rule_version=_string(data["rule_version"], "rule_version"),
        position=_integer(data["position"], "position"),
        requirement=_enum(data["requirement"], RuleRequirementV2, "requirement"),
        applicability_reference=_string(
            data["applicability_reference"], "applicability_reference"
        ),
        resource_reference_ids=tuple(
            _string(item, "resource_reference_id")
            for item in _array(
                data["resource_reference_ids"], "resource_reference_ids"
            )
        ),
        record_version=_string(data["record_version"], "record_version"),
    )


def _profile(value: Any) -> HardConstraintProfileRefV2:
    data = _object(
        value,
        (
            "profile_id",
            "profile_version",
            "theta_a_reference",
            "ordered_rule_specs",
            "resource_references",
            "declared_content_hash",
            "record_version",
        ),
        "HardConstraintProfileRefV2",
    )
    return HardConstraintProfileRefV2(
        profile_id=_string(data["profile_id"], "profile_id"),
        profile_version=_string(data["profile_version"], "profile_version"),
        theta_a_reference=_configuration(data["theta_a_reference"]),
        ordered_rule_specs=tuple(
            _rule_spec(item)
            for item in _array(data["ordered_rule_specs"], "ordered_rule_specs")
        ),
        resource_references=tuple(
            _resource(item)
            for item in _array(data["resource_references"], "resource_references")
        ),
        declared_content_hash=_optional_string(
            data["declared_content_hash"], "declared_content_hash"
        ),
        record_version=_string(data["record_version"], "record_version"),
    )


def _evidence(value: Any) -> EvidenceReferenceV2:
    data = _object(
        value,
        (
            "reference_namespace",
            "reference_id",
            "source_record_version",
            "record_version",
        ),
        "EvidenceReferenceV2",
    )
    return EvidenceReferenceV2(
        reference_namespace=_string(
            data["reference_namespace"], "reference_namespace"
        ),
        reference_id=_string(data["reference_id"], "reference_id"),
        source_record_version=_optional_string(
            data["source_record_version"], "source_record_version"
        ),
        record_version=_string(data["record_version"], "record_version"),
    )


def _rule_outcome(value: Any) -> ConstraintRuleOutcomeV2:
    data = _object(
        value,
        (
            "rule_outcome_id",
            "receipt_id",
            "field_id",
            "candidate",
            "c0_candidate",
            "rule_spec",
            "state",
            "attempted",
            "evidence_availability",
            "evidence_references",
            "outcome_reason_kind",
            "outcome_code",
            "outcome_detail",
            "theta_a_reference",
            "rule_profile_reference",
            "resource_references",
            "record_version",
        ),
        "ConstraintRuleOutcomeV2",
    )
    reason_kind = data["outcome_reason_kind"]
    return ConstraintRuleOutcomeV2(
        rule_outcome_id=_string(data["rule_outcome_id"], "rule_outcome_id"),
        receipt_id=_string(data["receipt_id"], "receipt_id"),
        field_id=_string(data["field_id"], "field_id"),
        candidate=_candidate(data["candidate"]),
        c0_candidate=_candidate(data["c0_candidate"]),
        rule_spec=_rule_spec(data["rule_spec"]),
        state=_enum(data["state"], RuleOutcomeStateV2, "state"),
        attempted=_boolean(data["attempted"], "attempted"),
        evidence_availability=_enum(
            data["evidence_availability"],
            RuleEvidenceAvailabilityV2,
            "evidence_availability",
        ),
        evidence_references=tuple(
            _evidence(item)
            for item in _array(data["evidence_references"], "evidence_references")
        ),
        outcome_reason_kind=(
            None
            if reason_kind is None
            else _enum(
                reason_kind,
                RuleOutcomeReasonKindV2,
                "outcome_reason_kind",
            )
        ),
        outcome_code=_optional_string(data["outcome_code"], "outcome_code"),
        outcome_detail=_optional_string(data["outcome_detail"], "outcome_detail"),
        theta_a_reference=_configuration(data["theta_a_reference"]),
        rule_profile_reference=_profile(data["rule_profile_reference"]),
        resource_references=tuple(
            _resource(item)
            for item in _array(data["resource_references"], "resource_references")
        ),
        record_version=_string(data["record_version"], "record_version"),
    )


def constraint_result_v2_from_json(payload: str) -> ConstraintResultV2:
    if not isinstance(payload, str) or not payload:
        raise HardConstraintSerializationError("payload must be a nonempty string.")
    if payload.startswith("\ufeff"):
        raise HardConstraintSerializationError("UTF-8 BOM is not permitted.")
    try:
        decoded = json.loads(payload, object_pairs_hook=_unique_json_object)
        data = _object(
            decoded,
            (
                "constraint_result_id",
                "receipt_id",
                "field_id",
                "candidate",
                "c0_candidate",
                "theta_a_reference",
                "rule_profile_reference",
                "rule_outcomes",
                "aggregate_state",
                "aggregate_reason",
                "record_version",
            ),
            "ConstraintResultV2",
        )
        return ConstraintResultV2(
            constraint_result_id=_string(
                data["constraint_result_id"], "constraint_result_id"
            ),
            receipt_id=_string(data["receipt_id"], "receipt_id"),
            field_id=_string(data["field_id"], "field_id"),
            candidate=_candidate(data["candidate"]),
            c0_candidate=_candidate(data["c0_candidate"]),
            theta_a_reference=_configuration(data["theta_a_reference"]),
            rule_profile_reference=_profile(data["rule_profile_reference"]),
            rule_outcomes=tuple(
                _rule_outcome(item)
                for item in _array(data["rule_outcomes"], "rule_outcomes")
            ),
            aggregate_state=_enum(
                data["aggregate_state"],
                ConstraintAggregateStateV2,
                "aggregate_state",
            ),
            aggregate_reason=_enum(
                data["aggregate_reason"],
                ConstraintAggregateReasonV2,
                "aggregate_reason",
            ),
            record_version=_string(data["record_version"], "record_version"),
        )
    except HardConstraintSerializationError:
        raise
    except (HardConstraintV2Error, TypeError, ValueError) as exc:
        raise HardConstraintSerializationError(
            "Serialized ConstraintResultV2 failed record validation."
        ) from exc


__all__ = [
    "ConstraintAggregateReasonV2",
    "ConstraintAggregateStateV2",
    "ConstraintResultV2",
    "ConstraintRuleOutcomeV2",
    "EvidenceReferenceV2",
    "HardConstraintAuditIntegrityError",
    "HardConstraintProfileConfigurationError",
    "HardConstraintResourceRefV2",
    "HardConstraintRuleSpecV2",
    "HardConstraintSerializationError",
    "HardConstraintSourceBindingError",
    "HardConstraintV2Error",
    "RECORD_VERSION_V2",
    "RuleEvidenceAvailabilityV2",
    "RuleOutcomeReasonKindV2",
    "RuleOutcomeStateV2",
    "RuleRequirementV2",
    "build_source_bound_constraint_result_v2",
    "constraint_result_v2_from_json",
    "constraint_result_v2_to_json",
]
