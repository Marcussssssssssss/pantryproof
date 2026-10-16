"""B2-as-c0 adapter for the provisional proposed-method contracts."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.baseline_b3 import (
    B3Result,
    B3RuleOutcome,
    EXTRACTOR_VERSION as B3_EXTRACTOR_VERSION,
)
from pipeline.contracts import (
    FieldStatus,
    PolicyState,
    PreResolutionDisposition,
    ReceiptExtractionStatus,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    StructuredField,
)
from pipeline.layout_b2 import (
    B2ExtractionResult,
    EXTRACTOR_VERSION as B2_EXTRACTOR_VERSION,
)
from pipeline.proposed.contracts import (
    B3CompatibleSeedV1,
    CandidateSourceKind,
    MethodReadyFieldV1,
    PROPOSED_CONTRACT_VERSION,
    SourceCharacterSpanV1,
)


class ProposedAdapterIntegrityError(ValueError):
    """The stored upstream records cannot form a trustworthy method boundary."""


@dataclass(frozen=True, slots=True)
class ProposedAdapterResultV1:
    """Method-ready extracted fields or the preserved B2 source fallback."""

    receipt_id: str
    original_b2_result: B2ExtractionResult
    stored_gate_result: SourceEvidenceGateResult
    b2_extraction_status: ReceiptExtractionStatus | None
    method_ready_fields: tuple[MethodReadyFieldV1, ...]
    excluded_b2_field_ids: tuple[str, ...]
    b3_seeds: tuple[B3CompatibleSeedV1, ...]
    fallback_disposition: PreResolutionDisposition | None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.receipt_id or not self.receipt_id.strip():
            raise ValueError("receipt_id must be non-empty.")
        if self.stored_gate_result.receipt_id != self.receipt_id:
            raise ValueError("The stored gate result must belong to the receipt.")
        if len(self.method_ready_fields) != len(
            {item.field_id for item in self.method_ready_fields}
        ):
            raise ValueError("Method-ready field IDs must be unique.")
        if len(self.excluded_b2_field_ids) != len(set(self.excluded_b2_field_ids)):
            raise ValueError("Excluded B2 field IDs must be unique.")
        if len(self.b3_seeds) != len({item.seed_id for item in self.b3_seeds}):
            raise ValueError("B3 seed IDs must be unique.")
        if any(item.receipt_id != self.receipt_id for item in self.method_ready_fields):
            raise ValueError("Method-ready fields must belong to the receipt.")
        if any(item.receipt_id != self.receipt_id for item in self.b3_seeds):
            raise ValueError("B3 seeds must belong to the receipt.")
        known_field_ids = {item.field_id for item in self.method_ready_fields}
        if any(item.field_id not in known_field_ids for item in self.b3_seeds):
            raise ValueError("A B3 seed must target a method-ready field.")

        if self.fallback_disposition is not None:
            if (
                self.fallback_disposition.state is not PolicyState.FALLBACK_NO_UPDATE
                or self.b2_extraction_status is not None
                or self.method_ready_fields
                or self.excluded_b2_field_ids
                or self.b3_seeds
            ):
                raise ValueError("A fallback adapter result cannot contain method fields.")
        elif self.b2_extraction_status is None:
            raise ValueError("Structured B2 input requires its extraction status.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


def adapt_b2_to_proposed(
    b2_result: B2ExtractionResult,
    b3_result: B3Result | None = None,
) -> ProposedAdapterResultV1:
    """Adapt already-computed B2/B3 records without rerunning upstream work.

    The adapter has no gate callback, OCR dependency, or extractor callback.  It
    consumes the stored gate result and keeps each exact extracted B2 value as
    permanent c0.  B3 differences are exposed only as possible future seeds.
    """

    if not isinstance(b2_result, B2ExtractionResult):
        raise TypeError("b2_result must be B2ExtractionResult.")
    if b3_result is not None and not isinstance(b3_result, B3Result):
        raise TypeError("b3_result must be B3Result when provided.")
    if b3_result is not None and b3_result.original_b2_result is not b2_result:
        raise ProposedAdapterIntegrityError(
            "B3 input must retain the exact B2 result supplied to the adapter."
        )
    if b3_result is not None and b3_result.ruleset_id != B3_EXTRACTOR_VERSION:
        raise ProposedAdapterIntegrityError("Unexpected B3 ruleset identifier.")

    output = b2_result.receipt_output
    if output is None:
        disposition = b2_result.pre_resolution_disposition
        if disposition is None:
            raise ProposedAdapterIntegrityError("B2 fallback is missing its disposition.")
        gate = disposition.gate_result
        if (
            gate.decision is not SourceEvidenceDecision.INSUFFICIENT
            or disposition.state is not PolicyState.FALLBACK_NO_UPDATE
        ):
            raise ProposedAdapterIntegrityError(
                "B2 output absence is valid only for recorded source insufficiency."
            )
        if b3_result is not None and b3_result.receipt_output is not None:
            raise ProposedAdapterIntegrityError("B3 cannot create output after fallback.")
        return ProposedAdapterResultV1(
            receipt_id=gate.receipt_id,
            original_b2_result=b2_result,
            stored_gate_result=gate,
            b2_extraction_status=None,
            method_ready_fields=(),
            excluded_b2_field_ids=(),
            b3_seeds=(),
            fallback_disposition=disposition,
        )

    if output.extractor_version != B2_EXTRACTOR_VERSION:
        raise ProposedAdapterIntegrityError(
            f"Expected exact B2 version {B2_EXTRACTOR_VERSION!r}."
        )
    gate = output.source_evidence.gate_result
    if gate.decision is not SourceEvidenceDecision.SUFFICIENT:
        raise ProposedAdapterIntegrityError(
            "Extracted B2 fields require a stored sufficient gate result."
        )
    if gate.receipt_id != output.receipt_id:
        raise ProposedAdapterIntegrityError("Gate and B2 receipt identities differ.")
    if b2_result.pre_resolution_disposition is not None:
        raise ProposedAdapterIntegrityError(
            "Structured B2 output cannot also carry a fallback disposition."
        )
    if b3_result is not None:
        _validate_b3_compatibility(output.receipt_id, output.source_evidence, b3_result)

    ordered_fields = _ordered_fields(output)
    seeds = _b3_seeds(ordered_fields, b3_result)
    seed_ids_by_field: dict[str, tuple[str, ...]] = {}
    for field_value in ordered_fields:
        seed_ids_by_field[field_value.field_id] = tuple(
            seed.seed_id for seed in seeds if seed.field_id == field_value.field_id
        )

    token_by_id = {
        token.token_id: token for token in output.source_evidence.tokens
    }
    method_fields: list[MethodReadyFieldV1] = []
    excluded: list[str] = []
    for field_value in ordered_fields:
        if field_value.status is not FieldStatus.EXTRACTED:
            excluded.append(field_value.field_id)
            continue
        assert field_value.value is not None
        method_fields.append(
            MethodReadyFieldV1(
                method_field_id=f"{field_value.field_id}:method:v1",
                receipt_id=output.receipt_id,
                field_id=field_value.field_id,
                field_name=field_value.field_name,
                original_b2_field=field_value,
                original_value=field_value.value,
                c0_candidate_id=f"{field_value.field_id}:c0",
                c0_value=field_value.value,
                source_token_ids=field_value.source_token_ids,
                source_tokens=tuple(
                    token_by_id[token_id] for token_id in field_value.source_token_ids
                ),
                source_image_id=output.source_evidence.image_id,
                source_processing_status=output.source_evidence.processing_status,
                b2_extraction_status=output.extraction_status,
                b2_extractor_version=output.extractor_version,
                stored_gate_result=gate,
                b3_ruleset_id=b3_result.ruleset_id if b3_result is not None else None,
                b3_seed_ids=seed_ids_by_field[field_value.field_id],
            )
        )

    return ProposedAdapterResultV1(
        receipt_id=output.receipt_id,
        original_b2_result=b2_result,
        stored_gate_result=gate,
        b2_extraction_status=output.extraction_status,
        method_ready_fields=tuple(method_fields),
        excluded_b2_field_ids=tuple(excluded),
        b3_seeds=seeds,
        fallback_disposition=None,
    )


def _validate_b3_compatibility(receipt_id: str, source_evidence, result: B3Result) -> None:
    if result.receipt_output is None:
        raise ProposedAdapterIntegrityError("Structured B2 input requires structured B3 input.")
    if result.receipt_output.receipt_id != receipt_id:
        raise ProposedAdapterIntegrityError("B3 and B2 receipt identities differ.")
    if result.receipt_output.source_evidence is not source_evidence:
        raise ProposedAdapterIntegrityError("B3 did not retain the exact source package.")


def _ordered_fields(output) -> tuple[StructuredField, ...]:
    values = [output.store_name, output.purchase_date]
    values.extend(field_value for item in output.items for field_value in item.fields)
    values.append(output.receipt_total)
    return tuple(values)


def _b3_seeds(
    ordered_fields: tuple[StructuredField, ...],
    b3_result: B3Result | None,
) -> tuple[B3CompatibleSeedV1, ...]:
    if b3_result is None:
        return ()
    original_by_id = {item.field_id: item for item in ordered_fields}
    event_by_id = {item.event_id: item for item in b3_result.rule_events}
    seed_inputs: list[
        tuple[str, str, CandidateSourceKind, tuple[str, ...], tuple[str, ...], tuple]
    ] = []
    seen: set[tuple[str, str]] = set()

    for relation in b3_result.field_transformations:
        original = original_by_id.get(relation.field_id)
        if original is None or original.status is not FieldStatus.EXTRACTED:
            continue
        if relation.transformed_field.value == original.value:
            continue
        relevant_events = tuple(
            event_by_id[event_id]
            for event_id in relation.event_ids
            if event_by_id[event_id].outcome
            in {
                B3RuleOutcome.REPRESENTATION_CHANGED,
                B3RuleOutcome.CANDIDATE_APPLIED,
            }
        )
        if not relevant_events:
            raise ProposedAdapterIntegrityError(
                "A differing B3 value lacks change-event provenance."
            )
        source_kind = (
            CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR
            if any(
                event.outcome is B3RuleOutcome.CANDIDATE_APPLIED
                for event in relevant_events
            )
            else CandidateSourceKind.GENERIC_NORMALIZATION
        )
        proposed = relation.transformed_field.value
        assert original.value is not None and proposed is not None
        spans = _unique_spans(
            span for event in relevant_events for span in event.source_slices
        )
        key = (relation.field_id, proposed)
        seen.add(key)
        seed_inputs.append(
            (
                relation.field_id,
                proposed,
                source_kind,
                tuple(event.event_id for event in relevant_events),
                _unique_strings(event.rule_id for event in relevant_events),
                spans,
            )
        )

    for candidate in b3_result.candidates:
        original = original_by_id[candidate.target_field_id]
        if original.status is not FieldStatus.EXTRACTED or candidate.value == original.value:
            continue
        key = (candidate.target_field_id, candidate.value)
        if key in seen:
            continue
        matching_events = tuple(
            event
            for event in b3_result.rule_events
            if candidate.target_field_id in event.target_field_ids
            and candidate.value in event.candidate_values
        )
        if not matching_events:
            raise ProposedAdapterIntegrityError("A B3 candidate lacks event provenance.")
        seen.add(key)
        seed_inputs.append(
            (
                candidate.target_field_id,
                candidate.value,
                CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                tuple(event.event_id for event in matching_events),
                _unique_strings(event.rule_id for event in matching_events),
                candidate.source_slices,
            )
        )

    seeds: list[B3CompatibleSeedV1] = []
    for index, (field_id, value, source_kind, event_ids, rule_ids, spans) in enumerate(
        seed_inputs
    ):
        original = original_by_id[field_id]
        assert original.value is not None
        seeds.append(
            B3CompatibleSeedV1(
                seed_id=f"{field_id}:b3-seed:{index:03d}",
                receipt_id=original.receipt_id,
                field_id=field_id,
                c0_candidate_id=f"{field_id}:c0",
                c0_value=original.value,
                proposed_value=value,
                source_kind=source_kind,
                b3_ruleset_id=b3_result.ruleset_id,
                b3_event_ids=event_ids,
                b3_rule_ids=rule_ids,
                source_spans=tuple(
                    SourceCharacterSpanV1(
                        token_id=span.token_id,
                        start=span.start,
                        end=span.end,
                        text=span.text,
                    )
                    for span in spans
                ),
            )
        )
    return tuple(seeds)


def _unique_strings(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _unique_spans(values) -> tuple:
    return tuple(dict.fromkeys(values))
