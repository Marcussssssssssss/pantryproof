"""Deterministic candidate-draft generation for the proposed method.

This component implements only the boundary between validated suspicion and
future candidate processing.  It preserves permanent B2 c0 and exposes
adapter-produced B3 seeds as source-bound drafts.  It deliberately does not
deduplicate, rank, limit, constrain, score, or materialize CandidateRecordV1.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pipeline.proposed.adapter import ProposedAdapterResultV1
from pipeline.proposed.contracts import (
    B3CompatibleSeedV1,
    CandidateSourceKind,
    MethodReadyFieldV1,
    SourceCharacterSpanV1,
)
from pipeline.proposed.suspicion import SuspicionResultV0


CANDIDATE_GENERATOR_VERSION = "candidate-draft-generator-v0"
CANDIDATE_GENERATION_RECORD_VERSION = "candidate-generation-record-v0"

CANDIDATE_SOURCE_ORDER = (
    CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
    CandidateSourceKind.GENERIC_NORMALIZATION,
    CandidateSourceKind.RETAILER_MAPPING,
    CandidateSourceKind.PANTRY_TERMINOLOGY,
)

_NO_SUSPICION_REASON = "Field is not suspicious; altered sources were not evaluated."
_UNAVAILABLE_RESOURCE_REASON = {
    CandidateSourceKind.RETAILER_MAPPING: (
        "No approved retailer-mapping runtime snapshot is configured."
    ),
    CandidateSourceKind.PANTRY_TERMINOLOGY: (
        "No approved pantry-terminology runtime snapshot is configured."
    ),
}


class CandidateGenerationIntegrityError(ValueError):
    """Upstream records cannot form a trustworthy candidate-draft boundary."""


class CandidateSourceEvaluationStatusV0(str, Enum):
    """Whether one altered-candidate source was evaluated in this component."""

    EVALUATED = "EVALUATED"
    NOT_EVALUATED_NO_SUSPICION = "NOT_EVALUATED_NO_SUSPICION"
    UNAVAILABLE_NOT_CONFIGURED = "UNAVAILABLE_NOT_CONFIGURED"


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _require_unique_text(values: tuple[str, ...], name: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{name} must contain non-empty strings.")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique.")


@dataclass(frozen=True, slots=True)
class OriginalCandidateDraftV0:
    """The exact method-ready B2 field retained as permanent c0."""

    method_ready_field: MethodReadyFieldV1
    c0_candidate_id: str
    value: str
    source_token_ids: tuple[str, ...]
    record_version: str = CANDIDATE_GENERATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.method_ready_field, MethodReadyFieldV1):
            raise TypeError("method_ready_field must be MethodReadyFieldV1.")
        _require_text(self.c0_candidate_id, "c0_candidate_id")
        _require_text(self.value, "value")
        _require_unique_text(self.source_token_ids, "source_token_ids")
        method = self.method_ready_field
        if self.c0_candidate_id != method.c0_candidate_id:
            raise ValueError("Original draft must retain the exact c0 candidate ID.")
        if self.value != method.c0_value or self.value != method.original_value:
            raise ValueError("Original draft must retain the exact unnormalized B2 value.")
        if self.source_token_ids != method.source_token_ids:
            raise ValueError("Original draft must retain B2 source-token order.")
        if self.record_version != CANDIDATE_GENERATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-generation record version.")


@dataclass(frozen=True, slots=True)
class AlteredCandidateProposalV0:
    """One source-bound B3 seed, before deduplication or candidate identity."""

    proposal_reference: str
    method_ready_field: MethodReadyFieldV1
    b3_seed: B3CompatibleSeedV1
    adapter_seed_position: int
    record_version: str = CANDIDATE_GENERATION_RECORD_VERSION

    def __post_init__(self) -> None:
        _require_text(self.proposal_reference, "proposal_reference")
        if not isinstance(self.method_ready_field, MethodReadyFieldV1):
            raise TypeError("method_ready_field must be MethodReadyFieldV1.")
        if not isinstance(self.b3_seed, B3CompatibleSeedV1):
            raise TypeError("b3_seed must be B3CompatibleSeedV1.")
        if type(self.adapter_seed_position) is not int or self.adapter_seed_position < 0:
            raise ValueError("adapter_seed_position must be a non-negative integer.")
        if self.proposal_reference != self.b3_seed.seed_id:
            raise ValueError("Proposal reference must be the existing B3 seed identity.")
        method = self.method_ready_field
        seed = self.b3_seed
        if (
            seed.receipt_id != method.receipt_id
            or seed.field_id != method.field_id
            or seed.c0_candidate_id != method.c0_candidate_id
            or seed.c0_value != method.c0_value
            or seed.b3_ruleset_id != method.b3_ruleset_id
        ):
            raise ValueError("Proposal seed must match the complete method-ready identity.")
        if seed.seed_id not in method.b3_seed_ids:
            raise ValueError("Proposal seed must be declared by the method-ready field.")
        if self.record_version != CANDIDATE_GENERATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-generation record version.")

    @property
    def proposed_value(self) -> str:
        return self.b3_seed.proposed_value

    @property
    def source_kind(self) -> CandidateSourceKind:
        return self.b3_seed.source_kind

    @property
    def b3_event_ids(self) -> tuple[str, ...]:
        return self.b3_seed.b3_event_ids

    @property
    def b3_rule_ids(self) -> tuple[str, ...]:
        return self.b3_seed.b3_rule_ids

    @property
    def source_spans(self) -> tuple[SourceCharacterSpanV1, ...]:
        return self.b3_seed.source_spans


@dataclass(frozen=True, slots=True)
class CandidateSourceStatusV0:
    """Auditable evaluation status for one thesis-permitted source category."""

    source_kind: CandidateSourceKind
    status: CandidateSourceEvaluationStatusV0
    proposal_references: tuple[str, ...] = ()
    reason: str | None = None
    record_version: str = CANDIDATE_GENERATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if self.source_kind not in CANDIDATE_SOURCE_ORDER:
            raise ValueError("Source status requires an altered-candidate source kind.")
        if not isinstance(self.status, CandidateSourceEvaluationStatusV0):
            raise TypeError("status must be CandidateSourceEvaluationStatusV0.")
        _require_unique_text(self.proposal_references, "proposal_references")
        if self.status is CandidateSourceEvaluationStatusV0.EVALUATED:
            if self.reason is not None:
                raise ValueError("An evaluated source must not carry an unavailable reason.")
        else:
            if self.proposal_references:
                raise ValueError("An unevaluated source cannot claim candidate proposals.")
            _require_text(self.reason or "", "reason")
        if self.record_version != CANDIDATE_GENERATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-generation record version.")


@dataclass(frozen=True, slots=True)
class CandidateGenerationResultV0:
    """Reconstructable output of the bounded candidate-draft generator."""

    suspicion_result: SuspicionResultV0
    adapter_result: ProposedAdapterResultV1
    original: OriginalCandidateDraftV0
    altered_proposals: tuple[AlteredCandidateProposalV0, ...]
    source_statuses: tuple[CandidateSourceStatusV0, ...]
    generator_version: str = CANDIDATE_GENERATOR_VERSION
    record_version: str = CANDIDATE_GENERATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.suspicion_result, SuspicionResultV0):
            raise TypeError("suspicion_result must be SuspicionResultV0.")
        if not isinstance(self.adapter_result, ProposedAdapterResultV1):
            raise TypeError("adapter_result must be ProposedAdapterResultV1.")
        if not isinstance(self.original, OriginalCandidateDraftV0):
            raise TypeError("original must be OriginalCandidateDraftV0.")
        if any(
            not isinstance(item, AlteredCandidateProposalV0)
            for item in self.altered_proposals
        ):
            raise TypeError("altered_proposals must contain proposal records.")
        if any(
            not isinstance(item, CandidateSourceStatusV0)
            for item in self.source_statuses
        ):
            raise TypeError("source_statuses must contain source-status records.")
        if self.generator_version != CANDIDATE_GENERATOR_VERSION:
            raise ValueError("Unsupported candidate generator version.")
        if self.record_version != CANDIDATE_GENERATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-generation record version.")

        expected = _derive_candidate_drafts(
            self.suspicion_result,
            self.adapter_result,
        )
        if self.original != expected[0]:
            raise ValueError("Original draft must equal the exact derived permanent c0.")
        if self.altered_proposals != expected[1]:
            raise ValueError(
                "Altered proposals must equal the canonical source-bound derivation."
            )
        if self.source_statuses != expected[2]:
            raise ValueError("Source statuses must equal the canonical source audit.")


def generate_candidate_drafts(
    *,
    suspicion_result: SuspicionResultV0,
    adapter_result: ProposedAdapterResultV1,
) -> CandidateGenerationResultV0:
    """Preserve c0 and expose only approved adapter B3 seeds as raw proposals."""

    if not isinstance(suspicion_result, SuspicionResultV0):
        raise TypeError("suspicion_result must be SuspicionResultV0.")
    if not isinstance(adapter_result, ProposedAdapterResultV1):
        raise TypeError("adapter_result must be ProposedAdapterResultV1.")
    original, proposals, statuses = _derive_candidate_drafts(
        suspicion_result,
        adapter_result,
    )
    return CandidateGenerationResultV0(
        suspicion_result=suspicion_result,
        adapter_result=adapter_result,
        original=original,
        altered_proposals=proposals,
        source_statuses=statuses,
    )


def _derive_candidate_drafts(
    suspicion_result: SuspicionResultV0,
    adapter_result: ProposedAdapterResultV1,
) -> tuple[
    OriginalCandidateDraftV0,
    tuple[AlteredCandidateProposalV0, ...],
    tuple[CandidateSourceStatusV0, ...],
]:
    method = _selected_method_field(suspicion_result, adapter_result)
    seeds_with_positions = _validated_field_seeds(method, adapter_result)
    _validate_source_spans(seeds_with_positions, method, adapter_result)

    original = OriginalCandidateDraftV0(
        method_ready_field=method,
        c0_candidate_id=method.c0_candidate_id,
        value=method.c0_value,
        source_token_ids=method.source_token_ids,
    )

    if not suspicion_result.is_suspicious:
        return original, (), tuple(
            CandidateSourceStatusV0(
                source_kind=source_kind,
                status=(
                    CandidateSourceEvaluationStatusV0.NOT_EVALUATED_NO_SUSPICION
                ),
                reason=_NO_SUSPICION_REASON,
            )
            for source_kind in CANDIDATE_SOURCE_ORDER
        )

    proposals = tuple(
        AlteredCandidateProposalV0(
            proposal_reference=seed.seed_id,
            method_ready_field=method,
            b3_seed=seed,
            adapter_seed_position=position,
        )
        for source_kind in CANDIDATE_SOURCE_ORDER[:2]
        for position, seed in seeds_with_positions
        if seed.source_kind is source_kind
    )
    references_by_source = {
        source_kind: tuple(
            proposal.proposal_reference
            for proposal in proposals
            if proposal.source_kind is source_kind
        )
        for source_kind in CANDIDATE_SOURCE_ORDER[:2]
    }
    statuses = (
        CandidateSourceStatusV0(
            source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
            status=CandidateSourceEvaluationStatusV0.EVALUATED,
            proposal_references=references_by_source[
                CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR
            ],
        ),
        CandidateSourceStatusV0(
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            status=CandidateSourceEvaluationStatusV0.EVALUATED,
            proposal_references=references_by_source[
                CandidateSourceKind.GENERIC_NORMALIZATION
            ],
        ),
        CandidateSourceStatusV0(
            source_kind=CandidateSourceKind.RETAILER_MAPPING,
            status=CandidateSourceEvaluationStatusV0.UNAVAILABLE_NOT_CONFIGURED,
            reason=_UNAVAILABLE_RESOURCE_REASON[
                CandidateSourceKind.RETAILER_MAPPING
            ],
        ),
        CandidateSourceStatusV0(
            source_kind=CandidateSourceKind.PANTRY_TERMINOLOGY,
            status=CandidateSourceEvaluationStatusV0.UNAVAILABLE_NOT_CONFIGURED,
            reason=_UNAVAILABLE_RESOURCE_REASON[
                CandidateSourceKind.PANTRY_TERMINOLOGY
            ],
        ),
    )
    return original, proposals, statuses


def _selected_method_field(
    suspicion_result: SuspicionResultV0,
    adapter_result: ProposedAdapterResultV1,
) -> MethodReadyFieldV1:
    method = suspicion_result.method_ready_field
    if adapter_result.receipt_id != method.receipt_id:
        raise CandidateGenerationIntegrityError(
            "Suspicion and adapter receipt identities differ."
        )
    matches = tuple(
        item
        for item in adapter_result.method_ready_fields
        if item.method_field_id == method.method_field_id
    )
    if len(matches) != 1:
        raise CandidateGenerationIntegrityError(
            "Suspicion must identify exactly one adapter method-ready field."
        )
    if matches[0] != method:
        raise CandidateGenerationIntegrityError(
            "Suspicion must retain the complete adapter method-ready field."
        )
    if adapter_result.stored_gate_result != method.stored_gate_result:
        raise CandidateGenerationIntegrityError(
            "Adapter and method-ready gate records differ."
        )

    output = adapter_result.original_b2_result.receipt_output
    if output is None or output.receipt_id != method.receipt_id:
        raise CandidateGenerationIntegrityError(
            "Candidate drafts require the matching structured B2 receipt output."
        )
    if output.source_evidence.gate_result != method.stored_gate_result:
        raise CandidateGenerationIntegrityError(
            "Original receipt evidence and method-ready gate records differ."
        )
    if method.source_image_id != output.source_evidence.image_id:
        raise CandidateGenerationIntegrityError(
            "Method-ready source image differs from the original B2 evidence."
        )
    if method.source_processing_status != output.source_evidence.processing_status:
        raise CandidateGenerationIntegrityError(
            "Method-ready source processing status differs from B2 evidence."
        )
    if method.b2_extraction_status != output.extraction_status:
        raise CandidateGenerationIntegrityError(
            "Method-ready extraction status differs from the B2 receipt output."
        )
    if method.b2_extractor_version != output.extractor_version:
        raise CandidateGenerationIntegrityError(
            "Method-ready extractor version differs from the B2 receipt output."
        )
    if adapter_result.b2_extraction_status != output.extraction_status:
        raise CandidateGenerationIntegrityError(
            "Adapter extraction status differs from the B2 receipt output."
        )
    if method.field_id in adapter_result.excluded_b2_field_ids:
        raise CandidateGenerationIntegrityError(
            "A selected method-ready field cannot also be excluded by the adapter."
        )
    receipt_fields = [output.store_name, output.purchase_date]
    receipt_fields.extend(field for row in output.items for field in row.fields)
    receipt_fields.append(output.receipt_total)
    original_matches = tuple(
        field for field in receipt_fields if field.field_id == method.field_id
    )
    if len(original_matches) != 1 or original_matches[0] != method.original_b2_field:
        raise CandidateGenerationIntegrityError(
            "Method-ready original field must equal the field in the B2 receipt output."
        )
    return method


def _validated_field_seeds(
    method: MethodReadyFieldV1,
    adapter_result: ProposedAdapterResultV1,
) -> tuple[tuple[int, B3CompatibleSeedV1], ...]:
    declared_ids = method.b3_seed_ids
    _require_unique_text(declared_ids, "method_ready_field.b3_seed_ids")

    adapter_ids = tuple(seed.seed_id for seed in adapter_result.b3_seeds)
    _require_unique_text(adapter_ids, "adapter_result B3 seed IDs")
    seeds_by_id = {seed.seed_id: seed for seed in adapter_result.b3_seeds}

    missing = tuple(seed_id for seed_id in declared_ids if seed_id not in seeds_by_id)
    if missing:
        raise CandidateGenerationIntegrityError(
            f"Declared B3 seed IDs are absent from the adapter: {missing!r}."
        )

    selected = tuple(
        (position, seed)
        for position, seed in enumerate(adapter_result.b3_seeds)
        if seed.field_id == method.field_id
    )
    selected_ids = tuple(seed.seed_id for _, seed in selected)
    undeclared = tuple(seed_id for seed_id in selected_ids if seed_id not in declared_ids)
    if undeclared:
        raise CandidateGenerationIntegrityError(
            f"Adapter contains undeclared B3 seeds for the field: {undeclared!r}."
        )
    wrong_field = tuple(
        seed_id
        for seed_id in declared_ids
        if seeds_by_id[seed_id].field_id != method.field_id
    )
    if wrong_field:
        raise CandidateGenerationIntegrityError(
            f"Declared B3 seed IDs target another field: {wrong_field!r}."
        )
    if set(selected_ids) != set(declared_ids) or len(selected_ids) != len(declared_ids):
        raise CandidateGenerationIntegrityError(
            "Declared and adapter B3 seed references must match exactly once."
        )

    for _, seed in selected:
        if (
            seed.receipt_id != method.receipt_id
            or seed.field_id != method.field_id
            or seed.c0_candidate_id != method.c0_candidate_id
            or seed.c0_value != method.c0_value
            or seed.b3_ruleset_id != method.b3_ruleset_id
        ):
            raise CandidateGenerationIntegrityError(
                f"B3 seed {seed.seed_id!r} contradicts method-ready identity."
            )
        if seed.source_kind not in CANDIDATE_SOURCE_ORDER[:2]:
            raise CandidateGenerationIntegrityError(
                f"B3 seed {seed.seed_id!r} has an unsupported source kind."
            )
        _require_unique_text(seed.b3_event_ids, f"{seed.seed_id} event IDs")
        _require_unique_text(seed.b3_rule_ids, f"{seed.seed_id} rule IDs")
    return selected


def _validate_source_spans(
    seeds_with_positions: tuple[tuple[int, B3CompatibleSeedV1], ...],
    method: MethodReadyFieldV1,
    adapter_result: ProposedAdapterResultV1,
) -> None:
    output = adapter_result.original_b2_result.receipt_output
    if output is None:
        raise CandidateGenerationIntegrityError("Structured source evidence is absent.")
    tokens = output.source_evidence.tokens
    token_ids = tuple(token.token_id for token in tokens)
    _require_unique_text(token_ids, "original receipt OCR token IDs")
    token_by_id = {token.token_id: token for token in tokens}
    for source_token_id, method_token in zip(
        method.source_token_ids,
        method.source_tokens,
        strict=True,
    ):
        original_token = token_by_id.get(source_token_id)
        if original_token is None or method_token != original_token:
            raise CandidateGenerationIntegrityError(
                "Method-ready source tokens must equal the original receipt OCR tokens."
            )

    for _, seed in seeds_with_positions:
        for span in seed.source_spans:
            token = token_by_id.get(span.token_id)
            if token is None:
                raise CandidateGenerationIntegrityError(
                    f"B3 seed {seed.seed_id!r} references unknown OCR token "
                    f"{span.token_id!r}."
                )
            if token.receipt_id != method.receipt_id:
                raise CandidateGenerationIntegrityError(
                    "A source span references a token from another receipt."
                )
            if (
                type(span.start) is not int
                or type(span.end) is not int
                or span.start < 0
                or span.end <= span.start
                or span.end > len(token.original_text)
            ):
                raise CandidateGenerationIntegrityError(
                    f"B3 seed {seed.seed_id!r} has invalid literal OCR offsets."
                )
            literal = token.original_text[span.start : span.end]
            if span.text != literal:
                raise CandidateGenerationIntegrityError(
                    f"B3 seed {seed.seed_id!r} source text does not equal the "
                    "original OCR token slice."
                )
