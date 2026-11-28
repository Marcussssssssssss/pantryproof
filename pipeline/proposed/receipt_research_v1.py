"""Connect the shared B2 receipt to the recovered offline research policy."""

from dataclasses import asdict, dataclass, replace
from enum import Enum
from hashlib import sha256
from typing import Callable

from evaluation.prediction_adapters import adapt_b2_result_to_prediction_receipt
from evaluation.prediction_schema import PredictionProvenance
from evaluation.research_policy_v0 import (
    CandidateEvidence, FrozenCalibration, FrozenScorer, VerificationPolicy, VerifiedField, verify_field,
)
from evaluation.research_runner_v0 import FieldDecision, SystemOutput, canonical_bytes, source_digest
from pipeline.baseline_b3 import parse_generic_date
from pipeline.contracts import FieldStatus, PolicyState, PreResolutionDisposition, ReceiptFieldName, ReceiptOutput
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed.contracts import CandidateAuditStatus, to_deterministic_json
from pipeline.proposed.receipt_context_v1 import replace_fields
from pipeline.proposed.receipt_correction_v1 import (
    PriceStatus, ReceiptCorrectionResult, ReceiptFieldEvidence, ReceiptMethodConfig,
    conflicting_numeric_changes, correct_receipt_v1,
)
from pipeline.proposed.receipt_resources_v1 import ReceiptResources, text_key


VERSION = "proposed-receipt-research-v1"
_PRICE_ROW_FIELDS = {
    ReceiptFieldName.ITEM_DESCRIPTION, ReceiptFieldName.QUANTITY, ReceiptFieldName.UNIT_PRICE,
}


class ResearchMethodState(str, Enum):
    NOT_READY = "NOT_READY"
    FALLBACK_NO_UPDATE = "FALLBACK_NO_UPDATE"
    POLICY_APPLIED = "POLICY_APPLIED"


@dataclass(frozen=True, slots=True)
class FieldVerificationSettings:
    pantry_relevant: bool
    policy: VerificationPolicy
    replacement_margin: float
    unresolved_conflict: bool


@dataclass(frozen=True, slots=True)
class ReceiptVerification:
    scorer: FrozenScorer
    calibration: FrozenCalibration
    settings_for: Callable[[ReceiptFieldEvidence], FieldVerificationSettings]

    def __post_init__(self):
        if self.calibration.scorer_sha256 != self.scorer.sha256:
            raise ValueError("Receipt verification requires the scorer bound to its calibration.")


@dataclass(frozen=True, slots=True)
class ProposedFieldAudit:
    decision: FieldDecision
    selected_candidate_id: str
    verifier_result: VerifiedField | None
    reason: str
    unresolved_conflict: bool | None = None


@dataclass(frozen=True, slots=True)
class ProposedReceiptResearchResult:
    state: ResearchMethodState
    correction: ReceiptCorrectionResult
    output: SystemOutput | None = None
    audits: tuple[ProposedFieldAudit, ...] = ()
    receipt_output: ReceiptOutput | None = None


def policy_candidate_evidence(result: ReceiptCorrectionResult) -> dict[str, tuple[CandidateEvidence, ...]]:
    """Project admitted vectors for fitting, calibration and selective verification."""
    if not result.fields:
        return {}
    ocr_sha256 = source_digest(result.baseline.receipt_output.source_evidence)
    inputs = {(row.field_id, row.candidate_id): row for row in result.scoring_inputs()}
    by_field = {}
    for field in result.fields:
        field_id = field.original.field_id
        admitted = []
        for candidate in field.candidates:
            row = inputs.get((field_id, candidate.candidate_id))
            if row is None:
                continue
            original = candidate is field.c0
            audit_payload = to_deterministic_json({
                "method": result.version,
                "ocr_sha256": ocr_sha256,
                "field_id": field_id,
                "c0": field.c0.candidate_id,
                "candidate": candidate,
                "resource_references": result.resource_references,
                "configuration": result.config,
                "region": result.region,
            })
            admitted.append(CandidateEvidence(
                candidate.candidate_id, candidate.value, original, True,
                bool(row.replacement_support),
                (not original and candidate.price is not None
                 and candidate.price.status is PriceStatus.PRICE_SUPPORTED),
                original or bool(row.replacement_support),
                "sha256:" + sha256(audit_payload.encode("utf-8")).hexdigest(),
                tuple(None if missing else float(value)
                      for value, missing in zip(row.values, row.missing_mask, strict=True)),
            ))
        by_field[field_id] = tuple(admitted)
    return by_field


def _decision_digest(field, settings, verified, reason, verification, ocr_sha256):
    return sha256(canonical_bytes({
        "source": ocr_sha256,
        "field_id": field.original.field_id,
        "c0": field.c0.candidate_id,
        "candidate_audit": to_deterministic_json(field.candidates),
        "settings": asdict(settings),
        "reason": reason,
        "scorer": verification.scorer.sha256,
        "calibration": verification.calibration.sha256,
        "verified": verified.decision.decision_evidence_sha256 if verified is not None else None,
    })).hexdigest()


def _review_original(field, settings, verified, reason, verification, ocr_sha256, conflict=None):
    evidence = _decision_digest(field, settings, verified, reason, verification, ocr_sha256)
    decision = FieldDecision(field.original.field_id, PolicyState.REVIEW_REQUIRED,
                             settings.pantry_relevant, field.c0.value, field.c0.value,
                             decision_evidence_sha256=evidence)
    return ProposedFieldAudit(decision, field.c0.candidate_id, verified, reason, conflict)


def _verify(field, candidates, settings, verification, ocr_sha256):
    if field.c0.audit_status is not CandidateAuditStatus.SCORING_ELIGIBLE:
        return _review_original(field, settings, None, "ORIGINAL_NOT_SCORING_ELIGIBLE",
                                verification, ocr_sha256)
    # Keep source-level conflicts in the same cached flag supplied to the policy.
    conflict = (settings.unresolved_conflict or field.proposal_limit_exceeded
                or field.reason == "CONFLICTING_NON_PRICE_EVIDENCE")
    verified = verify_field(
        field.original.field_id, settings.pantry_relevant, candidates, verification.scorer,
        verification.calibration, settings.policy, replacement_margin=settings.replacement_margin,
        unresolved_conflict=conflict,
    )
    evidence = _decision_digest(field, settings, verified, verified.reason, verification, ocr_sha256)
    decision = replace(verified.decision, decision_evidence_sha256=evidence)
    return ProposedFieldAudit(decision, verified.selected_candidate_id, verified, verified.reason, conflict)


def _project_field(field, audit):
    if audit.selected_candidate_id == field.c0.candidate_id:
        return replace(field.original, confidence=None)
    candidate = next(item for item in field.candidates if item.candidate_id == audit.selected_candidate_id)
    return replace(field.original, value=candidate.value, source_token_ids=candidate.output_token_ids,
                   status=FieldStatus.EXTRACTED, unresolved_reason=None, confidence=None)


def _price_context_conflicts(correction, terminology, projected, changed):
    store, date = correction.preview.store_name, correction.preview.purchase_date
    selected_store = projected[store.field_id].value
    selected_date = projected[date.field_id].value
    store_changed = text_key(selected_store or "") != text_key(store.value or "")
    if store_changed and terminology is not None:
        store_changed = terminology.retailer_id(selected_store) != terminology.retailer_id(store.value)
    date_changed = parse_generic_date(selected_date).normalized_value != parse_generic_date(date.value).normalized_value
    row_changes = tuple(projected[field_id] for field_id in changed
                        if projected[field_id].field_name in _PRICE_ROW_FIELDS)
    return {
        field.original.field_id for field in correction.fields
        if any(candidate.price is not None and candidate.price.status in
               (PriceStatus.PRICE_SUPPORTED, PriceStatus.PRICE_CONFLICT) for candidate in field.candidates)
        and (store_changed or date_changed or any(
            other.item_row_id == field.original.item_row_id and other.field_id != field.original.field_id
            for other in row_changes
        ))
    }


def run_proposed_receipt_v1(
    baseline: B2ExtractionResult, *, resources: ReceiptResources = ReceiptResources(),
    region: str | None = None, correction_config: ReceiptMethodConfig = ReceiptMethodConfig(),
    verification: ReceiptVerification | None = None,
) -> ProposedReceiptResearchResult:
    """Produce correction evidence, and apply an externally governed policy when supplied."""
    correction = correct_receipt_v1(baseline, resources=resources, region=region, config=correction_config)
    if correction.fallback_disposition is not None:
        return ProposedReceiptResearchResult(ResearchMethodState.FALLBACK_NO_UPDATE, correction)
    if verification is None:
        return ProposedReceiptResearchResult(ResearchMethodState.NOT_READY, correction)

    original_output = baseline.receipt_output
    source = original_output.source_evidence
    ocr_sha256 = source_digest(source)
    admitted = policy_candidate_evidence(correction)
    fields = {field.original.field_id: field for field in correction.fields}
    settings = {field_id: verification.settings_for(field) for field_id, field in fields.items()}
    audits = {field_id: _verify(field, admitted[field_id], settings[field_id], verification, ocr_sha256)
              for field_id, field in fields.items()}

    def revert(field_ids, reason):
        for field_id in field_ids:
            audits[field_id] = _review_original(fields[field_id], settings[field_id],
                                                audits[field_id].verifier_result, reason, verification,
                                                ocr_sha256, audits[field_id].unresolved_conflict)

    projected = {field_id: _project_field(field, audits[field_id]) for field_id, field in fields.items()}
    changed = {field_id for field_id, field in fields.items()
               if audits[field_id].selected_candidate_id != field.c0.candidate_id}
    price_conflicts = _price_context_conflicts(correction, resources.terminology, projected, changed)
    revert(price_conflicts, "PRICE_CONTEXT_CHANGED")
    for field_id in price_conflicts:
        projected[field_id] = _project_field(fields[field_id], audits[field_id])
    numeric_conflicts = conflicting_numeric_changes(
        original_output, correction.b3.adjustments, projected, changed - price_conflicts, require_exact=True,
    )
    revert(numeric_conflicts, "JOINT_ARITHMETIC_CONFLICT")
    for field_id in numeric_conflicts:
        projected[field_id] = _project_field(fields[field_id], audits[field_id])

    output = replace(replace_fields(original_output, projected), extractor_version=VERSION)
    prediction = adapt_b2_result_to_prediction_receipt(
        B2ExtractionResult(output, None),
        provenance=PredictionProvenance("ocr-" + ocr_sha256, ocr_sha256, VERSION),
        row_ordinals=tuple((row.row_id, ordinal) for ordinal, row in enumerate(output.items)),
        expected_version=VERSION,
    )
    decisions = tuple(audit.decision for audit in audits.values())
    state = (PolicyState.REVIEW_REQUIRED if any(
        decision.state is PolicyState.REVIEW_REQUIRED for decision in decisions
    ) else PolicyState.AUTO_RESOLVED)
    return ProposedReceiptResearchResult(
        ResearchMethodState.POLICY_APPLIED, correction,
        SystemOutput(prediction, PreResolutionDisposition(state, source.gate_result), decisions),
        tuple(audits.values()),
        output,
    )
