"""Verified input context for a future hard-constraint evaluator.

This synthetic-only boundary consumes one already-finalized candidate ledger.
It revalidates and preserves the existing receipt, source-gate, method-field,
adapter, and retained-candidate records.  It deliberately makes no constraint,
eligibility, scoring, calibration, review, or persistence decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pipeline.contracts import (
    FieldStatus,
    OcrSourceToken,
    OutputStage,
    ReceiptOutput,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
)
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed.adapter import ProposedAdapterResultV1
from pipeline.proposed.candidate_finalization import (
    BlockedCandidateFinalizationAuditV0,
    CandidateFinalizationCoverageStatusV0,
    CandidateFinalizationIntegrityError,
    CandidateFinalizationReadinessV0,
    CandidateFinalizationResultV0,
)
from pipeline.proposed.candidate_generation import CandidateGenerationResultV0
from pipeline.proposed.contracts import (
    CandidateLimitStatus,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
    ConfigurationRefV1,
    MethodReadyFieldV1,
)


HARD_CONSTRAINT_CONTEXT_COMPONENT_VERSION = "hard-constraint-context-v0"
HARD_CONSTRAINT_CONTEXT_RECORD_VERSION = "hard-constraint-context-record-v0"


class HardConstraintInputIntegrityError(ValueError):
    """Stored evidence is malformed or contradicts its upstream graph."""


class HardConstraintInputUnavailableReasonV0(str, Enum):
    """Operational reasons a valid finalization cannot enter this boundary."""

    RETAINED_PROVENANCE_BLOCKED = "RETAINED_PROVENANCE_BLOCKED"
    RANKING_UNAVAILABLE = "RANKING_UNAVAILABLE"


class HardConstraintInputUnavailableError(RuntimeError):
    """A valid upstream result is not ready for complete input preparation."""

    def __init__(
        self,
        reason: HardConstraintInputUnavailableReasonV0,
        finalization_result: CandidateFinalizationResultV0,
    ) -> None:
        if not isinstance(reason, HardConstraintInputUnavailableReasonV0):
            raise TypeError(
                "reason must be HardConstraintInputUnavailableReasonV0."
            )
        self.reason = reason
        self.finalization_result = finalization_result
        super().__init__(reason.value)


def _upstream_generation(
    finalization_result: CandidateFinalizationResultV0,
) -> CandidateGenerationResultV0:
    """Follow the approved stored graph without invoking a pipeline stage."""

    try:
        generation = (
            finalization_result.limit_result.ranking_result.provenance_result
            .identity_preparation.deduplication_result.candidate_drafts
        )
    except AttributeError as exc:
        raise HardConstraintInputIntegrityError(
            "The finalization result does not expose the approved upstream graph."
        ) from exc
    if not isinstance(generation, CandidateGenerationResultV0):
        raise HardConstraintInputIntegrityError(
            "The upstream graph does not terminate in CandidateGenerationResultV0."
        )
    return generation


def _require_ready_finalization(
    finalization_result: CandidateFinalizationResultV0,
) -> None:
    if not isinstance(finalization_result, CandidateFinalizationResultV0):
        raise TypeError(
            "finalization_result must be CandidateFinalizationResultV0."
        )
    try:
        finalization_result.__post_init__()
    except (TypeError, ValueError) as exc:
        raise HardConstraintInputIntegrityError(
            "Candidate finalization failed complete upstream reconstruction."
        ) from exc

    if (
        finalization_result.readiness
        is CandidateFinalizationReadinessV0.BLOCKED_BY_RETAINED_PROVENANCE
    ):
        raise HardConstraintInputUnavailableError(
            HardConstraintInputUnavailableReasonV0.RETAINED_PROVENANCE_BLOCKED,
            finalization_result,
        )
    if (
        finalization_result.readiness
        is CandidateFinalizationReadinessV0.RANKING_UNAVAILABLE
    ):
        raise HardConstraintInputUnavailableError(
            HardConstraintInputUnavailableReasonV0.RANKING_UNAVAILABLE,
            finalization_result,
        )
    if (
        finalization_result.readiness
        is not CandidateFinalizationReadinessV0.RETAINED_SET_STRUCTURALLY_FINALIZED
    ):
        raise HardConstraintInputIntegrityError(
            "Unsupported candidate-finalization readiness state."
        )


def _receipt_fields(output: ReceiptOutput) -> tuple[object, ...]:
    return (
        output.store_name,
        output.purchase_date,
        *(field for row in output.items for field in row.fields),
        output.receipt_total,
    )


def _revalidate_stored_receipt(
    adapter_result: ProposedAdapterResultV1,
    method_ready_field: MethodReadyFieldV1,
) -> tuple[B2ExtractionResult, ReceiptOutput]:
    """Validate stored receipt evidence without rerunning gate or extraction."""

    try:
        adapter_result.__post_init__()
        method_ready_field.__post_init__()
        b2_result = adapter_result.original_b2_result
        if not isinstance(b2_result, B2ExtractionResult):
            raise TypeError("Adapter original_b2_result has an unsupported type.")
        b2_result.__post_init__()
        output = b2_result.receipt_output
        if not isinstance(output, ReceiptOutput):
            raise ValueError(
                "Hard-constraint input preparation requires structured B2 output."
            )
        output.__post_init__()
        if output.output_stage is not OutputStage.PRE_REVIEW_AUTOMATIC:
            raise ValueError(
                "Stored B2 output must remain PRE_REVIEW_AUTOMATIC."
            )
        output.source_evidence.__post_init__()
        output.source_evidence.provenance.__post_init__()
        output.source_evidence.gate_result.__post_init__()
        for token in output.source_evidence.tokens:
            token.__post_init__()
        for field in _receipt_fields(output):
            field.__post_init__()
        for row in output.items:
            row.__post_init__()
    except (TypeError, ValueError) as exc:
        raise HardConstraintInputIntegrityError(
            "Stored adapter, method-ready field, or B2 receipt failed revalidation."
        ) from exc
    return b2_result, output


def _validate_method_and_adapter(
    generation: CandidateGenerationResultV0,
) -> tuple[MethodReadyFieldV1, ProposedAdapterResultV1, ReceiptOutput]:
    method = generation.original.method_ready_field
    adapter = generation.adapter_result
    if not isinstance(method, MethodReadyFieldV1):
        raise HardConstraintInputIntegrityError(
            "The original candidate draft lacks a method-ready field."
        )
    if not isinstance(adapter, ProposedAdapterResultV1):
        raise HardConstraintInputIntegrityError(
            "The generation result lacks its proposed adapter record."
        )
    suspicion_method = generation.suspicion_result.method_ready_field
    if suspicion_method != method:
        raise HardConstraintInputIntegrityError(
            "Suspicion and original-candidate method-ready records differ."
        )

    matches = tuple(
        item
        for item in adapter.method_ready_fields
        if item.method_field_id == method.method_field_id
    )
    if len(matches) != 1 or matches[0] != method:
        raise HardConstraintInputIntegrityError(
            "The adapter must contain one complete matching method-ready field."
        )
    if method.field_id in adapter.excluded_b2_field_ids:
        raise HardConstraintInputIntegrityError(
            "A method-ready field cannot also be excluded by the adapter."
        )

    _, output = _revalidate_stored_receipt(adapter, method)
    evidence = output.source_evidence
    gate = adapter.stored_gate_result
    if (
        gate != method.stored_gate_result
        or gate != evidence.gate_result
        or gate.decision is not SourceEvidenceDecision.SUFFICIENT
    ):
        raise HardConstraintInputIntegrityError(
            "Stored source-gate evidence is absent, insufficient, or contradictory."
        )
    if adapter.fallback_disposition is not None:
        raise HardConstraintInputIntegrityError(
            "Structured method input cannot retain a fallback disposition."
        )
    if (
        adapter.receipt_id != method.receipt_id
        or output.receipt_id != method.receipt_id
        or evidence.receipt_id != method.receipt_id
        or gate.receipt_id != method.receipt_id
    ):
        raise HardConstraintInputIntegrityError(
            "Receipt identity differs across method, adapter, output, or gate."
        )
    if method.original_b2_field.status is not FieldStatus.EXTRACTED:
        raise HardConstraintInputIntegrityError(
            "Only an EXTRACTED B2 field can enter hard-constraint preparation."
        )
    field_matches = tuple(
        field for field in _receipt_fields(output) if field.field_id == method.field_id
    )
    if len(field_matches) != 1 or field_matches[0] != method.original_b2_field:
        raise HardConstraintInputIntegrityError(
            "The method-ready original field differs from the stored B2 output."
        )
    if (
        method.original_b2_field.value != method.original_value
        or method.original_value != method.c0_value
    ):
        raise HardConstraintInputIntegrityError(
            "Permanent c0 must equal the exact original B2 field value."
        )
    if (
        method.source_image_id != evidence.image_id
        or method.source_processing_status != evidence.processing_status
        or method.b2_extraction_status != output.extraction_status
        or adapter.b2_extraction_status != output.extraction_status
        or method.b2_extractor_version != output.extractor_version
    ):
        raise HardConstraintInputIntegrityError(
            "Stored image, processing, extraction, or extractor metadata differs."
        )

    token_by_id = {token.token_id: token for token in evidence.tokens}
    if len(token_by_id) != len(evidence.tokens):
        raise HardConstraintInputIntegrityError(
            "Original receipt OCR token identities are not unique."
        )
    if method.original_b2_field.source_token_ids != method.source_token_ids:
        raise HardConstraintInputIntegrityError(
            "Method-ready source references differ from the original B2 field."
        )
    if tuple(token.token_id for token in method.source_tokens) != method.source_token_ids:
        raise HardConstraintInputIntegrityError(
            "Method-ready source-token order differs from its token IDs."
        )
    for token_id, token in zip(
        method.source_token_ids, method.source_tokens, strict=True
    ):
        if token_by_id.get(token_id) != token:
            raise HardConstraintInputIntegrityError(
                "Method-ready source tokens differ from stored receipt OCR evidence."
            )
    return method, adapter, output


def _validate_original_candidate(
    original: CandidateRecordV1,
    method: MethodReadyFieldV1,
) -> None:
    try:
        original.__post_init__()
        for provenance in original.provenance:
            provenance.__post_init__()
    except (TypeError, ValueError) as exc:
        raise HardConstraintInputIntegrityError(
            "Permanent c0 failed shared candidate revalidation."
        ) from exc
    if (
        original.role is not CandidateRole.ORIGINAL
        or original.limit_status is not CandidateLimitStatus.RETAINED
        or original.candidate_id != method.c0_candidate_id
        or original.c0_candidate_id != method.c0_candidate_id
        or original.receipt_id != method.receipt_id
        or original.field_id != method.field_id
        or original.value != method.c0_value
    ):
        raise HardConstraintInputIntegrityError(
            "Permanent c0 contradicts the method-ready original."
        )
    if len(original.provenance) != 1:
        raise HardConstraintInputIntegrityError(
            "Permanent c0 requires its single canonical original provenance member."
        )
    provenance = original.provenance[0]
    if (
        provenance.source_kind is not CandidateSourceKind.ORIGINAL
        or provenance.original_observed_value != method.c0_value
        or provenance.source_token_ids != method.source_token_ids
    ):
        raise HardConstraintInputIntegrityError(
            "Permanent c0 provenance differs from original B2 source evidence."
        )


def _validate_theta_chain(
    finalization_result: CandidateFinalizationResultV0,
    generation: CandidateGenerationResultV0,
) -> None:
    limiting = finalization_result.limiting_configuration
    ranking = finalization_result.limit_result.ranking_result.configuration
    suspicion = generation.suspicion_result.theta_a_ref
    try:
        limiting.__post_init__()
        ranking.__post_init__()
        suspicion.__post_init__()
    except (TypeError, ValueError) as exc:
        raise HardConstraintInputIntegrityError(
            "Inherited synthetic Theta_A configuration failed revalidation."
        ) from exc
    if limiting.theta_a_ref != ranking.theta_a_ref or ranking.theta_a_ref != suspicion:
        raise HardConstraintInputIntegrityError(
            "The stored pipeline stages do not share one Theta_A reference."
        )


def _expected_context(
    finalization_result: CandidateFinalizationResultV0,
) -> tuple[
    MethodReadyFieldV1,
    ProposedAdapterResultV1,
    tuple[CandidateRecordV1, ...],
]:
    _require_ready_finalization(finalization_result)
    generation = _upstream_generation(finalization_result)
    method, adapter, _ = _validate_method_and_adapter(generation)
    _validate_theta_chain(finalization_result, generation)
    original = finalization_result.original_candidate
    _validate_original_candidate(original, method)

    candidates = (original, *finalization_result.retained_records)
    candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise HardConstraintInputIntegrityError(
            "Prepared candidates cannot contain duplicate candidate identities."
        )
    for candidate in candidates[1:]:
        try:
            candidate.__post_init__()
        except (TypeError, ValueError) as exc:
            raise HardConstraintInputIntegrityError(
                "A retained altered candidate failed shared-record revalidation."
            ) from exc
        if (
            candidate.role is not CandidateRole.ALTERED
            or candidate.limit_status is not CandidateLimitStatus.RETAINED
            or candidate.receipt_id != method.receipt_id
            or candidate.field_id != method.field_id
            or candidate.c0_candidate_id != method.c0_candidate_id
        ):
            raise HardConstraintInputIntegrityError(
                "A retained altered candidate contradicts the method-ready field."
            )
    overflow_ids = {
        candidate.candidate_id for candidate in finalization_result.overflow_records
    }
    if overflow_ids.intersection(candidate_ids):
        raise HardConstraintInputIntegrityError(
            "Overflow candidates cannot enter the prepared candidate tuple."
        )
    return method, adapter, candidates


@dataclass(frozen=True, slots=True)
class HardConstraintInputResultV0:
    """Exact stored context prepared for a future constraint evaluator."""

    finalization_result: CandidateFinalizationResultV0
    method_ready_field: MethodReadyFieldV1
    adapter_result: ProposedAdapterResultV1
    candidates: tuple[CandidateRecordV1, ...]
    component_version: str = HARD_CONSTRAINT_CONTEXT_COMPONENT_VERSION
    record_version: str = HARD_CONSTRAINT_CONTEXT_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.finalization_result, CandidateFinalizationResultV0):
            raise TypeError(
                "finalization_result must be CandidateFinalizationResultV0."
            )
        if not isinstance(self.method_ready_field, MethodReadyFieldV1):
            raise TypeError("method_ready_field must be MethodReadyFieldV1.")
        if not isinstance(self.adapter_result, ProposedAdapterResultV1):
            raise TypeError("adapter_result must be ProposedAdapterResultV1.")
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(candidate, CandidateRecordV1)
            for candidate in self.candidates
        ):
            raise TypeError("candidates must be a tuple of CandidateRecordV1.")
        if self.component_version != HARD_CONSTRAINT_CONTEXT_COMPONENT_VERSION:
            raise ValueError("Unsupported hard-constraint context component version.")
        if self.record_version != HARD_CONSTRAINT_CONTEXT_RECORD_VERSION:
            raise ValueError("Unsupported hard-constraint context record version.")

        try:
            expected_method, expected_adapter, expected_candidates = (
                _expected_context(self.finalization_result)
            )
        except HardConstraintInputUnavailableError as exc:
            raise HardConstraintInputIntegrityError(
                "An existing prepared context cannot reconstruct "
                "from unavailable finalization."
            ) from exc
        if self.method_ready_field is not expected_method:
            raise HardConstraintInputIntegrityError(
                "Prepared method-ready field must be the exact upstream graph object."
            )
        if self.adapter_result is not expected_adapter:
            raise HardConstraintInputIntegrityError(
                "Prepared adapter must be the exact upstream graph object."
            )
        if len(self.candidates) != len(expected_candidates) or any(
            observed is not expected
            for observed, expected in zip(
                self.candidates, expected_candidates, strict=True
            )
        ):
            raise HardConstraintInputIntegrityError(
                "Prepared candidates must retain exact c0-first upstream references."
            )

    @property
    def original_b2_result(self) -> B2ExtractionResult:
        return self.adapter_result.original_b2_result

    @property
    def receipt_output(self) -> ReceiptOutput:
        output = self.original_b2_result.receipt_output
        if output is None:  # Protected by reconstruction; keeps the type boundary exact.
            raise HardConstraintInputIntegrityError(
                "Structured B2 receipt output is unexpectedly absent."
            )
        return output

    @property
    def source_evidence(self) -> ReceiptSourceEvidence:
        return self.receipt_output.source_evidence

    @property
    def stored_gate(self) -> SourceEvidenceGateResult:
        return self.adapter_result.stored_gate_result

    @property
    def source_tokens(self) -> tuple[OcrSourceToken, ...]:
        return self.method_ready_field.source_tokens

    @property
    def source_image_id(self) -> str:
        return self.method_ready_field.source_image_id

    @property
    def overflow_audit_records(self) -> tuple[CandidateRecordV1, ...]:
        return self.finalization_result.overflow_records

    @property
    def blocked_audits(self) -> tuple[BlockedCandidateFinalizationAuditV0, ...]:
        return self.finalization_result.blocked_audits

    @property
    def full_ledger_coverage_status(self) -> CandidateFinalizationCoverageStatusV0:
        return self.finalization_result.coverage.status

    @property
    def receipt_id(self) -> str:
        return self.method_ready_field.receipt_id

    @property
    def field_id(self) -> str:
        return self.method_ready_field.field_id

    @property
    def theta_a_ref(self) -> ConfigurationRefV1:
        return self.finalization_result.limiting_configuration.theta_a_ref


def prepare_hard_constraint_inputs(
    *,
    finalization_result: CandidateFinalizationResultV0,
) -> HardConstraintInputResultV0:
    """Prepare exact c0-first retained inputs without evaluating constraints."""

    method, adapter, candidates = _expected_context(finalization_result)
    return HardConstraintInputResultV0(
        finalization_result=finalization_result,
        method_ready_field=method,
        adapter_result=adapter,
        candidates=candidates,
    )
