"""Bounded purchase-date calendar-validity hard-rule evaluator V0.

This module evaluates one exact retained D3 purchase-date candidate and emits
one Contract V2 rule outcome.  It deliberately does not aggregate outcomes,
select candidates, modify permanent c0, or implement controller policy.
"""

from __future__ import annotations

import re
import unicodedata

from pipeline import baseline_b3 as _b3
from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.contracts import CandidateRecordV1
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintRuleOutcomeV2,
    EvidenceReferenceV2,
    HardConstraintAuditIntegrityError,
    HardConstraintProfileRefV2,
    RuleEvidenceAvailabilityV2,
    RuleOutcomeReasonKindV2,
    RuleOutcomeStateV2,
    RuleRequirementV2,
)
from pipeline.proposed.hard_constraint_operands import (
    CandidateOperandAuditV0,
    HardConstraintOperandAuditResultV0,
)


PURCHASE_DATE_CALENDAR_VALIDITY_COMPONENT_VERSION = (
    "purchase-date-calendar-validity-v0"
)
PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID = "PURCHASE_DATE_CALENDAR_VALIDITY_V0"
PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION = "v0"
PURCHASE_DATE_GRAMMAR_REFERENCE = "PURCHASE_DATE_GRAMMAR_V0"
PURCHASE_DATE_PROFILE_ID = "purchase-date-calendar-validity-profile-v0"
PURCHASE_DATE_PROFILE_VERSION = "v0"
PURCHASE_DATE_APPLICABILITY_REFERENCE = "PURCHASE_DATE_ONLY_V0"
CANDIDATE_RECORD_EVIDENCE_NAMESPACE = "CANDIDATE_RECORD_V1"

APPROVED_B3_RULESET_ID = "B3-generic-rules-v0"
APPROVED_B3_SOURCE_BLOB = "73a929fe68c5459ea20c944069bf2cb05e86982a"

CALENDAR_DATE_IMPOSSIBLE = "CALENDAR_DATE_IMPOSSIBLE"
AMBIGUOUS_DATE_INTERPRETATION = "AMBIGUOUS_DATE_INTERPRETATION"
DATE_FORMAT_UNSUPPORTED = "DATE_FORMAT_UNSUPPORTED"

CALENDAR_DATE_IMPOSSIBLE_DETAIL = (
    "All interpretations permitted by the approved purchase-date grammar are "
    "calendar-invalid."
)
AMBIGUOUS_DATE_INTERPRETATION_DETAIL = (
    "Multiple distinct calendar-valid interpretations; no unique date established."
)
DATE_FORMAT_UNSUPPORTED_DETAIL = (
    "Candidate literal does not match the approved purchase-date grammar."
)


class PurchaseDateCalendarValidityError(ValueError):
    """Base error for the bounded purchase-date evaluator."""


class PurchaseDateConfigurationError(PurchaseDateCalendarValidityError):
    """The declared rule, profile, grammar, or parser version is incompatible."""


class PurchaseDateParserCompatibilityError(PurchaseDateConfigurationError):
    """The approved grammar mirror and public B3 parser no longer agree."""


class PurchaseDateIntegrityError(PurchaseDateCalendarValidityError):
    """A supplied stored record is malformed or internally contradictory."""


class PurchaseDateSourceBindingError(PurchaseDateCalendarValidityError):
    """The candidate or evidence reference is not the exact approved source."""


class PurchaseDateEvaluationError(RuntimeError):
    """The public B3 parser failed unexpectedly during bounded evaluation."""


# This separately versioned mirror recognizes syntax only.  Calendar validity
# and interpretations always come from the approved public B3 parser.
_YEAR_FIRST_DATE_RE = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
)
_NUMERIC_DATE_RE = re.compile(
    r"(?P<first>\d{1,2})(?P<separator>[/-])(?P<second>\d{1,2})"
    r"(?P=separator)(?P<year>\d{4})"
)
_MONTH_NAMES = (
    r"JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|"
    r"JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|"
    r"NOV(?:EMBER)?|DEC(?:EMBER)?"
)
_DAY_MONTH_NAME_RE = re.compile(
    rf"(?P<day>\d{{1,2}})\s+(?P<month>{_MONTH_NAMES})\s+"
    r"(?P<year>\d{4})",
    re.IGNORECASE,
)
_MONTH_NAME_DAY_RE = re.compile(
    rf"(?P<month>{_MONTH_NAMES})\s+(?P<day>\d{{1,2}}),?\s+"
    r"(?P<year>\d{4})",
    re.IGNORECASE,
)
_DATE_PATTERNS = (
    _YEAR_FIRST_DATE_RE,
    _NUMERIC_DATE_RE,
    _DAY_MONTH_NAME_RE,
    _MONTH_NAME_DAY_RE,
)


def recognizes_purchase_date_grammar_v0(value: str) -> bool:
    r"""Return whether ``value`` matches the approved B3-compatible syntax.

    The mirror preserves B3's NFKC, outer trimming, Unicode ``\d``, whitespace,
    separator, and Python ``re.IGNORECASE`` behavior.  It does not determine
    calendar validity.
    """

    if not isinstance(value, str):
        raise TypeError("value must be a string.")
    observed = unicodedata.normalize("NFKC", value).strip()
    return any(pattern.fullmatch(observed) is not None for pattern in _DATE_PATTERNS)


def _validate_profile(
    profile: HardConstraintProfileRefV2,
    operand_audit: HardConstraintOperandAuditResultV0,
) -> None:
    if not isinstance(profile, HardConstraintProfileRefV2):
        raise PurchaseDateConfigurationError(
            "rule_profile_reference must be HardConstraintProfileRefV2."
        )
    try:
        profile.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise PurchaseDateConfigurationError(
            "The purchase-date rule profile failed Contract V2 validation."
        ) from exc

    if profile.profile_id != PURCHASE_DATE_PROFILE_ID:
        raise PurchaseDateConfigurationError("Unexpected purchase-date profile ID.")
    if profile.profile_version != PURCHASE_DATE_PROFILE_VERSION:
        raise PurchaseDateConfigurationError("Unexpected purchase-date profile version.")
    if profile.resource_references:
        raise PurchaseDateConfigurationError(
            "The purchase-date V0 profile must not declare external resources."
        )
    if len(profile.ordered_rule_specs) != 1:
        raise PurchaseDateConfigurationError(
            "The purchase-date V0 profile requires exactly one rule."
        )

    rule = profile.ordered_rule_specs[0]
    if (
        rule.rule_id != PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID
        or rule.rule_version != PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION
        or rule.position != 0
        or rule.requirement is not RuleRequirementV2.MANDATORY
        or rule.applicability_reference != PURCHASE_DATE_APPLICABILITY_REFERENCE
        or rule.resource_reference_ids
    ):
        raise PurchaseDateConfigurationError(
            "The purchase-date rule specification is incompatible with V0."
        )

    theta_a = operand_audit.hard_constraint_input.theta_a_ref
    if profile.theta_a_reference != theta_a:
        raise PurchaseDateConfigurationError(
            "The profile Theta_A reference differs from the exact D3 input."
        )


def _validate_source_binding(
    operand_audit: HardConstraintOperandAuditResultV0,
    candidate_audit: CandidateOperandAuditV0,
    evidence_reference: EvidenceReferenceV2,
) -> tuple[CandidateRecordV1, CandidateRecordV1]:
    if not isinstance(operand_audit, HardConstraintOperandAuditResultV0):
        raise PurchaseDateIntegrityError(
            "operand_audit must be HardConstraintOperandAuditResultV0."
        )
    if not isinstance(candidate_audit, CandidateOperandAuditV0):
        raise PurchaseDateIntegrityError(
            "candidate_audit must be CandidateOperandAuditV0."
        )
    try:
        operand_audit.__post_init__()
        candidate_audit.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise PurchaseDateIntegrityError(
            "The D3 operand graph failed complete reconstruction."
        ) from exc

    if not any(stored is candidate_audit for stored in operand_audit.candidate_audits):
        raise PurchaseDateSourceBindingError(
            "candidate_audit is not the exact D3 aggregate member."
        )

    candidate = candidate_audit.candidate
    retained = operand_audit.hard_constraint_input.candidates
    if not retained or not any(stored is candidate for stored in retained):
        raise PurchaseDateSourceBindingError(
            "The audited candidate is not an exact retained D3 candidate."
        )
    c0_candidate = retained[0]
    if candidate.c0_candidate_id != c0_candidate.candidate_id:
        raise PurchaseDateSourceBindingError(
            "The audited candidate is not bound to the permanent D3 c0."
        )

    target = candidate_audit.target_field
    if target.field_name is not ReceiptFieldName.PURCHASE_DATE:
        raise PurchaseDateSourceBindingError(
            "PURCHASE_DATE_CALENDAR_VALIDITY_V0 requires a purchase-date target."
        )
    if target.receipt_id != candidate.receipt_id or target.field_id != candidate.field_id:
        raise PurchaseDateSourceBindingError(
            "The candidate identity differs from its purchase-date target."
        )

    if not isinstance(evidence_reference, EvidenceReferenceV2):
        raise PurchaseDateIntegrityError(
            "candidate_evidence_reference must be EvidenceReferenceV2."
        )
    try:
        evidence_reference.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise PurchaseDateIntegrityError(
            "The candidate evidence reference is structurally invalid."
        ) from exc
    if (
        evidence_reference.reference_namespace
        != CANDIDATE_RECORD_EVIDENCE_NAMESPACE
        or evidence_reference.reference_id != candidate.candidate_id
        or evidence_reference.source_record_version != candidate.record_version
    ):
        raise PurchaseDateSourceBindingError(
            "CANDIDATE_RECORD_V1 does not identify the exact audited candidate."
        )
    return candidate, c0_candidate


def _parse_candidate_literal(value: str) -> tuple[bool, _b3.DateParseResult]:
    if _b3.EXTRACTOR_VERSION != APPROVED_B3_RULESET_ID:
        raise PurchaseDateParserCompatibilityError(
            "The imported B3 ruleset is not the approved compatibility version."
        )

    recognized = recognizes_purchase_date_grammar_v0(value)
    try:
        parsed = _b3.parse_generic_date(value)
    except Exception as exc:
        raise PurchaseDateEvaluationError(
            "The public B3 date parser failed unexpectedly."
        ) from exc

    if not isinstance(parsed, _b3.DateParseResult):
        raise PurchaseDateParserCompatibilityError(
            "The public B3 parser returned an incompatible result type."
        )
    if parsed.original != value or not isinstance(parsed.state, _b3.B3ParseState):
        raise PurchaseDateParserCompatibilityError(
            "The public B3 parser changed literal or state semantics."
        )
    if not isinstance(parsed.interpretations, tuple) or any(
        not isinstance(item, str) or not item for item in parsed.interpretations
    ):
        raise PurchaseDateParserCompatibilityError(
            "The public B3 parser returned malformed interpretations."
        )
    if len(parsed.interpretations) != len(set(parsed.interpretations)):
        raise PurchaseDateParserCompatibilityError(
            "The public B3 parser did not collapse duplicate interpretations."
        )

    if parsed.state is _b3.B3ParseState.VALID:
        if (
            not recognized
            or not isinstance(parsed.normalized_value, str)
            or not parsed.normalized_value
            or parsed.interpretations != (parsed.normalized_value,)
        ):
            raise PurchaseDateParserCompatibilityError(
                "B3 VALID behavior differs from the approved grammar contract."
            )
    elif parsed.state is _b3.B3ParseState.AMBIGUOUS:
        if recognized is False or parsed.normalized_value is not None or len(
            parsed.interpretations
        ) < 2:
            raise PurchaseDateParserCompatibilityError(
                "B3 AMBIGUOUS behavior differs from the approved grammar contract."
            )
    elif parsed.state is _b3.B3ParseState.INVALID:
        if parsed.normalized_value is not None or parsed.interpretations:
            raise PurchaseDateParserCompatibilityError(
                "B3 INVALID behavior differs from the approved grammar contract."
            )
    else:  # pragma: no cover - protected by exact enum validation above.
        raise PurchaseDateParserCompatibilityError(
            "The public B3 parser returned an unsupported state."
        )

    return recognized, parsed


def evaluate_purchase_date_calendar_validity_v0(
    *,
    rule_outcome_id: str,
    operand_audit: HardConstraintOperandAuditResultV0,
    candidate_audit: CandidateOperandAuditV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    grammar_reference: str,
    candidate_evidence_reference: EvidenceReferenceV2,
) -> ConstraintRuleOutcomeV2:
    """Evaluate one exact retained purchase-date candidate.

    The returned record is candidate-level only.  Callers must still use the
    existing source-bound Contract V2 factory for complete profile aggregation.
    """

    if not isinstance(rule_outcome_id, str) or not rule_outcome_id.strip():
        raise PurchaseDateIntegrityError("rule_outcome_id must be nonempty.")
    if grammar_reference != PURCHASE_DATE_GRAMMAR_REFERENCE:
        raise PurchaseDateConfigurationError(
            "Unexpected purchase-date grammar reference."
        )

    candidate, c0_candidate = _validate_source_binding(
        operand_audit,
        candidate_audit,
        candidate_evidence_reference,
    )
    _validate_profile(rule_profile_reference, operand_audit)
    recognized, parsed = _parse_candidate_literal(candidate.value)

    reason_kind: RuleOutcomeReasonKindV2 | None
    outcome_code: str | None
    outcome_detail: str | None
    if not recognized:
        state = RuleOutcomeStateV2.UNAVAILABLE
        availability = RuleEvidenceAvailabilityV2.UNAVAILABLE
        reason_kind = RuleOutcomeReasonKindV2.UNAVAILABILITY
        outcome_code = DATE_FORMAT_UNSUPPORTED
        outcome_detail = DATE_FORMAT_UNSUPPORTED_DETAIL
    elif parsed.state is _b3.B3ParseState.VALID:
        state = RuleOutcomeStateV2.PASS
        availability = RuleEvidenceAvailabilityV2.AVAILABLE
        reason_kind = None
        outcome_code = None
        outcome_detail = None
    elif parsed.state is _b3.B3ParseState.AMBIGUOUS:
        state = RuleOutcomeStateV2.UNAVAILABLE
        availability = RuleEvidenceAvailabilityV2.UNAVAILABLE
        reason_kind = RuleOutcomeReasonKindV2.UNAVAILABILITY
        outcome_code = AMBIGUOUS_DATE_INTERPRETATION
        outcome_detail = AMBIGUOUS_DATE_INTERPRETATION_DETAIL
    else:
        state = RuleOutcomeStateV2.FAIL
        availability = RuleEvidenceAvailabilityV2.AVAILABLE
        reason_kind = RuleOutcomeReasonKindV2.FAILURE
        outcome_code = CALENDAR_DATE_IMPOSSIBLE
        outcome_detail = CALENDAR_DATE_IMPOSSIBLE_DETAIL

    try:
        return ConstraintRuleOutcomeV2(
            rule_outcome_id=rule_outcome_id,
            receipt_id=candidate.receipt_id,
            field_id=candidate.field_id,
            candidate=candidate,
            c0_candidate=c0_candidate,
            rule_spec=rule_profile_reference.ordered_rule_specs[0],
            state=state,
            attempted=True,
            evidence_availability=availability,
            evidence_references=(candidate_evidence_reference,),
            outcome_reason_kind=reason_kind,
            outcome_code=outcome_code,
            outcome_detail=outcome_detail,
            theta_a_reference=rule_profile_reference.theta_a_reference,
            rule_profile_reference=rule_profile_reference,
            resource_references=(),
        )
    except (HardConstraintAuditIntegrityError, TypeError, ValueError) as exc:
        raise PurchaseDateIntegrityError(
            "The bounded G2A outcome failed Contract V2 validation."
        ) from exc
