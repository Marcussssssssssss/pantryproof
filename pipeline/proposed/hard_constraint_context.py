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
    ReceiptItemRow,
    ReceiptOutput,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProvenance,
    StructuredField,
)
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed import hard_constraint_context_replay_meter_v1 as hc
from pipeline.proposed.candidate_deduplication import CandidateDeduplicationResultV0
from pipeline.proposed.candidate_identity import CandidateIdentityPreparationResultV0
from pipeline.proposed.candidate_limiting import CandidateLimitResultV0
from pipeline.proposed.candidate_provenance import CandidateProvenanceMaterializationResultV0
from pipeline.proposed.candidate_ranking import PreliminaryCandidateRankingResultV0
from pipeline.proposed.suspicion import SuspicionResultV0
from pipeline.proposed.adapter import ProposedAdapterResultV1
from pipeline.proposed.candidate_finalization import (
    BlockedCandidateFinalizationAuditV0,
    CandidateFinalizationCoverageStatusV0,
    CandidateFinalizationIntegrityError,
    CandidateFinalizationReadinessV0,
    CandidateFinalizationResultV0,
)
from pipeline.proposed.candidate_generation import CandidateGenerationResultV0, OriginalCandidateDraftV0
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
        limit = finalization_result.limit_result
        hc.exact(limit, CandidateLimitResultV0)
        ranking = limit.ranking_result
        hc.exact(ranking, PreliminaryCandidateRankingResultV0)
        provenance = ranking.provenance_result
        hc.exact(provenance, CandidateProvenanceMaterializationResultV0)
        preparation = provenance.identity_preparation
        hc.exact(preparation, CandidateIdentityPreparationResultV0)
        deduplication = preparation.deduplication_result
        hc.exact(deduplication, CandidateDeduplicationResultV0)
        generation = deduplication.candidate_drafts
        hc.exact(generation, CandidateGenerationResultV0)
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
    hc.exact(finalization_result, CandidateFinalizationResultV0)
    if not isinstance(finalization_result, CandidateFinalizationResultV0):
        raise TypeError(
            "finalization_result must be CandidateFinalizationResultV0."
        )
    try:
        hc.population(finalization_result.retained_records, finalization_result.overflow_records,
                      finalization_result.blocked_audits)
        hc.reserve(max_upstream_replays=1, max_work_units=1)
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
    if hc.selected() is not None:
        rows = len(output.items)
        fields = 3 + 4 * rows
        hc.sequence(fields)
        # The starred expression builds a list before converting to a tuple.
        hc.reserve(max_scan_items=rows, max_temporary_slots=fields + 4 * rows,
                   max_work_units=fields + 5 * rows)
    return (
        output.store_name,
        output.purchase_date,
        *(field for row in output.items for field in row.fields),
        output.receipt_total,
    )


@hc.operation
def _revalidate_stored_receipt(
    adapter_result: ProposedAdapterResultV1,
    method_ready_field: MethodReadyFieldV1,
) -> tuple[B2ExtractionResult, ReceiptOutput]:
    """Validate stored receipt evidence without rerunning gate or extraction."""

    try:
        hc.validate_adapter(adapter_result)
        hc.validate_method(method_ready_field)
        b2_result = adapter_result.original_b2_result
        if not isinstance(b2_result, B2ExtractionResult):
            raise TypeError("Adapter original_b2_result has an unsupported type.")
        hc.validate_plain(b2_result, B2ExtractionResult)
        output = b2_result.receipt_output
        if not isinstance(output, ReceiptOutput):
            raise ValueError(
                "Hard-constraint input preparation requires structured B2 output."
            )
        hc.validate_receipt(output)
        if output.output_stage is not OutputStage.PRE_REVIEW_AUTOMATIC:
            raise ValueError(
                "Stored B2 output must remain PRE_REVIEW_AUTOMATIC."
            )
        evidence = output.source_evidence
        hc.validate_evidence(evidence)
        hc.validate_plain(evidence.provenance, SourceProvenance)
        hc.validate_gate(evidence.gate_result)
        if hc.selected() is not None:
            hc.scan(len(evidence.tokens) + len(output.items))
        for token in evidence.tokens:
            hc.validate_plain(token, OcrSourceToken)
        for field in _receipt_fields(output):
            hc.validate_field(field)
        for row in output.items:
            hc.validate_plain(row, ReceiptItemRow)
    except (TypeError, ValueError) as exc:
        raise HardConstraintInputIntegrityError(
            "Stored adapter, method-ready field, or B2 receipt failed revalidation."
        ) from exc
    hc.reserve(max_temporary_slots=2, max_work_units=2)
    return b2_result, output


@hc.operation
def _validate_method_and_adapter(
    generation: CandidateGenerationResultV0,
) -> tuple[MethodReadyFieldV1, ProposedAdapterResultV1, ReceiptOutput]:
    hc.exact(generation.original, OriginalCandidateDraftV0)
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
    hc.exact(generation.suspicion_result, SuspicionResultV0)
    suspicion_method = generation.suspicion_result.method_ready_field
    hc.exact(adapter, ProposedAdapterResultV1)
    hc.admit_method_relationships(method, adapter, suspicion_method)
    if hc.not_equal(suspicion_method, method):
        raise HardConstraintInputIntegrityError(
            "Suspicion and original-candidate method-ready records differ."
        )

    matches = tuple(
        item
        for item in adapter.method_ready_fields
        if hc.equal(item.method_field_id, method.method_field_id)
    )
    if len(matches) != 1 or hc.not_equal(matches[0], method):
        raise HardConstraintInputIntegrityError(
            "The adapter must contain one complete matching method-ready field."
        )
    if hc.excluded(method.field_id, adapter.excluded_b2_field_ids):
        raise HardConstraintInputIntegrityError(
            "A method-ready field cannot also be excluded by the adapter."
        )

    hc.preflight_stored_b2(adapter)
    _, output = _revalidate_stored_receipt(adapter, method)
    evidence = output.source_evidence
    gate = adapter.stored_gate_result
    if (
        hc.not_equal(gate, method.stored_gate_result)
        or hc.not_equal(gate, evidence.gate_result)
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
        hc.not_equal(adapter.receipt_id, method.receipt_id)
        or hc.not_equal(output.receipt_id, method.receipt_id)
        or hc.not_equal(evidence.receipt_id, method.receipt_id)
        or hc.not_equal(gate.receipt_id, method.receipt_id)
    ):
        raise HardConstraintInputIntegrityError(
            "Receipt identity differs across method, adapter, output, or gate."
        )
    if method.original_b2_field.status is not FieldStatus.EXTRACTED:
        raise HardConstraintInputIntegrityError(
            "Only an EXTRACTED B2 field can enter hard-constraint preparation."
        )
    if hc.selected() is not None:
        hc.sequence(3 + 4 * len(output.items))
    field_matches = tuple(
        field for field in _receipt_fields(output) if hc.equal(field.field_id, method.field_id)
    )
    if len(field_matches) != 1 or hc.not_equal(field_matches[0], method.original_b2_field):
        raise HardConstraintInputIntegrityError(
            "The method-ready original field differs from the stored B2 output."
        )
    if (
        hc.not_equal(method.original_b2_field.value, method.original_value)
        or hc.not_equal(method.original_value, method.c0_value)
    ):
        raise HardConstraintInputIntegrityError(
            "Permanent c0 must equal the exact original B2 field value."
        )
    if (
        hc.not_equal(method.source_image_id, evidence.image_id)
        or hc.not_equal(method.source_processing_status, evidence.processing_status)
        or hc.not_equal(method.b2_extraction_status, output.extraction_status)
        or hc.not_equal(adapter.b2_extraction_status, output.extraction_status)
        or hc.not_equal(method.b2_extractor_version, output.extractor_version)
    ):
        raise HardConstraintInputIntegrityError(
            "Stored image, processing, extraction, or extractor metadata differs."
        )

    selected = hc.selected() is not None
    if selected:
        hc.sequence(len(evidence.tokens))
        duplicate = hc.has_duplicate_ids(tuple(token.token_id for token in evidence.tokens))
    else:
        token_by_id = {token.token_id: token for token in evidence.tokens}
        duplicate = len(token_by_id) != len(evidence.tokens)
    if duplicate:
        raise HardConstraintInputIntegrityError(
            "Original receipt OCR token identities are not unique."
        )
    if hc.not_equal(method.original_b2_field.source_token_ids, method.source_token_ids):
        raise HardConstraintInputIntegrityError(
            "Method-ready source references differ from the original B2 field."
        )
    if selected:
        hc.sequence(len(method.source_tokens))
    if hc.not_equal(tuple(token.token_id for token in method.source_tokens), method.source_token_ids):
        raise HardConstraintInputIntegrityError(
            "Method-ready source-token order differs from its token IDs."
        )
    if selected:
        hc.scan(len(method.source_tokens))
    for token_id, token in zip(
        method.source_token_ids, method.source_tokens, strict=True
    ):
        observed = hc.token_lookup(evidence.tokens, token_id) if selected else token_by_id.get(token_id)
        if hc.not_equal(observed, token):
            raise HardConstraintInputIntegrityError(
                "Method-ready source tokens differ from stored receipt OCR evidence."
            )
    hc.reserve(max_temporary_slots=3, max_work_units=3)
    return method, adapter, output


@hc.operation
def _validate_original_candidate(
    original: CandidateRecordV1,
    method: MethodReadyFieldV1,
) -> None:
    try:
        hc.validate_candidate(original)
        if hc.selected() is not None:
            hc.scan(len(original.provenance))
        for provenance in original.provenance:
            hc.validate_provenance(provenance)
    except (TypeError, ValueError) as exc:
        raise HardConstraintInputIntegrityError(
            "Permanent c0 failed shared candidate revalidation."
        ) from exc
    if (
        original.role is not CandidateRole.ORIGINAL
        or original.limit_status is not CandidateLimitStatus.RETAINED
        or hc.not_equal(original.candidate_id, method.c0_candidate_id)
        or hc.not_equal(original.c0_candidate_id, method.c0_candidate_id)
        or hc.not_equal(original.receipt_id, method.receipt_id)
        or hc.not_equal(original.field_id, method.field_id)
        or hc.not_equal(original.value, method.c0_value)
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
        or hc.not_equal(provenance.original_observed_value, method.c0_value)
        or hc.not_equal(provenance.source_token_ids, method.source_token_ids)
    ):
        raise HardConstraintInputIntegrityError(
            "Permanent c0 provenance differs from original B2 source evidence."
        )


@hc.operation
def _validate_theta_chain(
    finalization_result: CandidateFinalizationResultV0,
    generation: CandidateGenerationResultV0,
) -> None:
    limiting = finalization_result.limiting_configuration
    ranking = finalization_result.limit_result.ranking_result.configuration
    suspicion = generation.suspicion_result.theta_a_ref
    try:
        hc.reserve(max_work_units=2)
        limiting.__post_init__()
        ranking.__post_init__()
        hc.validate_plain(suspicion, ConfigurationRefV1)
    except (TypeError, ValueError) as exc:
        raise HardConstraintInputIntegrityError(
            "Inherited synthetic Theta_A configuration failed revalidation."
        ) from exc
    if (hc.not_equal(limiting.theta_a_ref, ranking.theta_a_ref)
            or hc.not_equal(ranking.theta_a_ref, suspicion)):
        raise HardConstraintInputIntegrityError(
            "The stored pipeline stages do not share one Theta_A reference."
        )


@hc.operation
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

    selected = hc.selected() is not None
    if selected:
        count = len(finalization_result.retained_records)
        hc.sequence(1 + count)
        hc.sequence(1 + count)
        hc.reserve(max_temporary_slots=1 + count, max_work_units=1 + count)
    candidates = (original, *finalization_result.retained_records)
    candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
    if hc.has_duplicate_ids(candidate_ids):
        raise HardConstraintInputIntegrityError(
            "Prepared candidates cannot contain duplicate candidate identities."
        )
    if selected:
        hc.sequence(len(candidates) - 1)
        hc.scan(len(candidates) - 1)
    for candidate in candidates[1:]:
        try:
            hc.validate_candidate(candidate)
        except (TypeError, ValueError) as exc:
            raise HardConstraintInputIntegrityError(
                "A retained altered candidate failed shared-record revalidation."
            ) from exc
        if (
            candidate.role is not CandidateRole.ALTERED
            or candidate.limit_status is not CandidateLimitStatus.RETAINED
            or hc.not_equal(candidate.receipt_id, method.receipt_id)
            or hc.not_equal(candidate.field_id, method.field_id)
            or hc.not_equal(candidate.c0_candidate_id, method.c0_candidate_id)
        ):
            raise HardConstraintInputIntegrityError(
                "A retained altered candidate contradicts the method-ready field."
            )
    if hc.has_overlap(finalization_result.overflow_records, candidate_ids):
        raise HardConstraintInputIntegrityError(
            "Overflow candidates cannot enter the prepared candidate tuple."
        )
    hc.reserve(max_temporary_slots=3, max_work_units=3)
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

    @hc.operation
    def __post_init__(self) -> None:
        hc.exact(self, HardConstraintInputResultV0)
        hc.exact(self.finalization_result, CandidateFinalizationResultV0)
        hc.exact(self.method_ready_field, MethodReadyFieldV1)
        hc.exact(self.adapter_result, ProposedAdapterResultV1)
        if hc.selected() is not None:
            hc.population(self.candidates)
            hc.scan(len(self.candidates))
            for candidate in self.candidates:
                hc.exact(candidate, CandidateRecordV1)
        if not isinstance(self.finalization_result, CandidateFinalizationResultV0):
            raise TypeError(
                "finalization_result must be CandidateFinalizationResultV0."
            )
        if not isinstance(self.method_ready_field, MethodReadyFieldV1):
            raise TypeError("method_ready_field must be MethodReadyFieldV1.")
        if not isinstance(self.adapter_result, ProposedAdapterResultV1):
            raise TypeError("adapter_result must be ProposedAdapterResultV1.")
        if hc.selected() is None and (not isinstance(self.candidates, tuple) or any(
            not isinstance(candidate, CandidateRecordV1)
            for candidate in self.candidates
        )):
            raise TypeError("candidates must be a tuple of CandidateRecordV1.")
        if hc.not_equal(self.component_version, HARD_CONSTRAINT_CONTEXT_COMPONENT_VERSION):
            raise ValueError("Unsupported hard-constraint context component version.")
        if hc.not_equal(self.record_version, HARD_CONSTRAINT_CONTEXT_RECORD_VERSION):
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
        if hc.selected() is not None:
            hc.scan(len(self.candidates))
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


@hc.operation
def prepare_hard_constraint_inputs(
    *,
    finalization_result: CandidateFinalizationResultV0,
) -> HardConstraintInputResultV0:
    """Prepare exact c0-first retained inputs without evaluating constraints."""

    method, adapter, candidates = _expected_context(finalization_result)
    hc.reserve(max_records=1, max_temporary_slots=6, max_work_units=6)
    return HardConstraintInputResultV0(
        finalization_result=finalization_result,
        method_ready_field=method,
        adapter_result=adapter,
        candidates=candidates,
    )
