"""Synthetic adversarial tests for candidate-draft generation V0."""

from __future__ import annotations

import inspect
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from unittest.mock import patch

from pipeline.baseline_b3 import apply_b3
from pipeline.contracts import (
    OcrSourceToken,
    Point,
    ReceiptExtractionStatus,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)
from pipeline.layout_b2 import extract_b2
from pipeline.proposed.adapter import ProposedAdapterResultV1, adapt_b2_to_proposed
from pipeline.proposed.candidate_generation import (
    AlteredCandidateProposalV0,
    CandidateGenerationIntegrityError,
    CandidateGenerationResultV0,
    CandidateSourceEvaluationStatusV0,
    CandidateSourceStatusV0,
    OriginalCandidateDraftV0,
    generate_candidate_drafts,
)
from pipeline.proposed.contracts import (
    B3CompatibleSeedV1,
    CandidateRecordV1,
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    MethodReadyFieldV1,
    SourceCharacterSpanV1,
)
from pipeline.proposed.suspicion import (
    ConfidenceAggregationV0,
    ConfidenceRuleV0,
    SuspicionConfigurationV0,
    SuspicionContextV0,
    SuspicionResultV0,
    UpstreamObservationStateV0,
    UpstreamObservationV0,
    UpstreamSignalV0,
    detect_suspicion,
)


class ProposedCandidateGenerationTests(unittest.TestCase):
    RECEIPT_ID = "candidate-draft-receipt"
    CONTEXT_BUILDER = "candidate-draft-test-context"

    def token(
        self,
        token_id: str,
        text: str,
        x: float,
        y: float,
        width: float = 50,
    ) -> OcrSourceToken:
        return OcrSourceToken(
            receipt_id=self.RECEIPT_ID,
            token_id=token_id,
            original_text=text,
            polygon=(
                Point(x, y),
                Point(x + width, y),
                Point(x + width, y + 10),
                Point(x, y + 10),
            ),
            raw_confidence=0.91,
        )

    def tokens(self) -> tuple[OcrSourceToken, ...]:
        return (
            self.token("store", "ＰＡＮＴＲＹ MART", 10, 0, 150),
            self.token("date-label", "DATE:", 10, 20, 40),
            self.token("date-value", "13/10/2026", 65, 20, 90),
            self.token("description", "MILK", 10, 45, 45),
            self.token("quantity", "2", 90, 45, 10),
            self.token("multiply", "x", 110, 45, 8),
            self.token("unit", "RM 5.50", 135, 45, 55),
            self.token("line-total", "11.00", 215, 45, 45),
            self.token("total-label", "TOTAL", 135, 80, 55),
            self.token("total-value", "11.00", 215, 80, 45),
        )

    def evidence(self) -> ReceiptSourceEvidence:
        gate = SourceEvidenceGateResult(
            gate_result_id=f"{self.RECEIPT_ID}:gate",
            receipt_id=self.RECEIPT_ID,
            decision=SourceEvidenceDecision.SUFFICIENT,
        )
        return ReceiptSourceEvidence(
            receipt_id=self.RECEIPT_ID,
            image_id=f"{self.RECEIPT_ID}:image",
            provenance=SourceProvenance(
                source_system="synthetic-unit-test",
                source_reference="memory://candidate-draft-receipt",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=self.tokens(),
            gate_result=gate,
        )

    def base_adapter(self) -> tuple[ProposedAdapterResultV1, MethodReadyFieldV1]:
        b2 = extract_b2(self.evidence())
        b3 = apply_b3(b2)
        adapter = adapt_b2_to_proposed(b2, b3)
        method = next(
            item
            for item in adapter.method_ready_fields
            if item.field_id.endswith("store-name")
        )
        return adapter, method

    def store_token(self, adapter: ProposedAdapterResultV1) -> OcrSourceToken:
        output = adapter.original_b2_result.receipt_output
        assert output is not None
        return next(
            token for token in output.source_evidence.tokens if token.token_id == "store"
        )

    def seed(
        self,
        method: MethodReadyFieldV1,
        *,
        suffix: str,
        source_kind: CandidateSourceKind,
        proposed_value: str,
        spans: tuple[SourceCharacterSpanV1, ...] = (),
        event_ids: tuple[str, ...] | None = None,
        rule_ids: tuple[str, ...] | None = None,
    ) -> B3CompatibleSeedV1:
        assert method.b3_ruleset_id is not None
        return B3CompatibleSeedV1(
            seed_id=f"{method.field_id}:synthetic-seed:{suffix}",
            receipt_id=method.receipt_id,
            field_id=method.field_id,
            c0_candidate_id=method.c0_candidate_id,
            c0_value=method.c0_value,
            proposed_value=proposed_value,
            source_kind=source_kind,
            b3_ruleset_id=method.b3_ruleset_id,
            b3_event_ids=event_ids or (f"event:{suffix}",),
            b3_rule_ids=rule_ids or (f"rule:{suffix}",),
            source_spans=spans,
        )

    def valid_span(
        self,
        adapter: ProposedAdapterResultV1,
        *,
        start: int = 0,
        end: int = 3,
    ) -> SourceCharacterSpanV1:
        token = self.store_token(adapter)
        return SourceCharacterSpanV1(
            token_id=token.token_id,
            start=start,
            end=end,
            text=token.original_text[start:end],
        )

    def adapter_with_seeds(
        self,
        adapter: ProposedAdapterResultV1,
        method: MethodReadyFieldV1,
        seeds: tuple[B3CompatibleSeedV1, ...],
        *,
        declared_ids: tuple[str, ...] | None = None,
    ) -> tuple[ProposedAdapterResultV1, MethodReadyFieldV1]:
        declared_ids = (
            tuple(seed.seed_id for seed in seeds)
            if declared_ids is None
            else declared_ids
        )
        updated_method = replace(method, b3_seed_ids=declared_ids)
        method_fields = tuple(
            updated_method if item.field_id == method.field_id else item
            for item in adapter.method_ready_fields
        )
        unrelated_seeds = tuple(
            item for item in adapter.b3_seeds if item.field_id != method.field_id
        )
        updated_adapter = replace(
            adapter,
            method_ready_fields=method_fields,
            b3_seeds=seeds + unrelated_seeds,
        )
        return updated_adapter, updated_method

    def adapter_with_method(
        self,
        adapter: ProposedAdapterResultV1,
        original_method: MethodReadyFieldV1,
        updated_method: MethodReadyFieldV1,
    ) -> ProposedAdapterResultV1:
        return replace(
            adapter,
            method_ready_fields=tuple(
                updated_method if item.field_id == original_method.field_id else item
                for item in adapter.method_ready_fields
            ),
        )

    def configuration(self, method: MethodReadyFieldV1) -> SuspicionConfigurationV0:
        theta = ConfigurationRefV1(
            kind=ConfigurationKind.THETA_A,
            configuration_id="theta-a-candidate-draft-test",
            configuration_version="test-v1",
            state=ConfigurationState.READY,
            content_hash="sha256:synthetic-candidate-draft-test",
        )
        return SuspicionConfigurationV0(
            theta_a_ref=theta,
            ocr_confidence_rule=ConfidenceRuleV0(
                rule_id="candidate-draft-ocr-confidence",
                score_source="synthetic-ocr-source",
                aggregation=ConfidenceAggregationV0.MIN_ALL_REFERENCED,
                threshold=Decimal("0.50"),
                domain_minimum=Decimal("0.00"),
                domain_maximum=Decimal("1.00"),
            ),
            extractor_confidence_rule=ConfidenceRuleV0(
                rule_id="candidate-draft-extractor-confidence",
                score_source=method.b2_extractor_version,
                aggregation=ConfidenceAggregationV0.DIRECT,
                threshold=Decimal("0.50"),
                domain_minimum=Decimal("0.00"),
                domain_maximum=Decimal("1.00"),
            ),
            context_builder_id=self.CONTEXT_BUILDER,
            context_builder_version="test-v1",
        )

    def observation(
        self,
        method: MethodReadyFieldV1,
        signal: UpstreamSignalV0,
        state: UpstreamObservationStateV0,
    ) -> UpstreamObservationV0:
        evidence_ids = (
            f"{method.field_id}:{signal.value.lower()}:evidence",
        )
        return UpstreamObservationV0(
            observation_id=f"{method.field_id}:{signal.value.lower()}:observation",
            receipt_id=method.receipt_id,
            field_id=method.field_id,
            signal=signal,
            state=state,
            provider_id=self.CONTEXT_BUILDER,
            provider_version="test-v1",
            evidence_ids=evidence_ids,
            reason=(
                None
                if state is UpstreamObservationStateV0.PASS
                else "Synthetic upstream suspicion trigger."
            ),
        )

    def suspicion(
        self,
        method: MethodReadyFieldV1,
        *,
        suspicious: bool,
    ) -> SuspicionResultV0:
        states = {
            signal: (
                UpstreamObservationStateV0.FAIL
                if suspicious and signal is UpstreamSignalV0.PARSE_TYPE
                else UpstreamObservationStateV0.PASS
            )
            for signal in UpstreamSignalV0
        }
        observations = {
            signal: self.observation(method, signal, state)
            for signal, state in states.items()
        }
        context = SuspicionContextV0(
            context_id=f"{method.method_field_id}:candidate-draft-context",
            receipt_id=method.receipt_id,
            method_field_id=method.method_field_id,
            field_id=method.field_id,
            gate_result_id=method.stored_gate_result.gate_result_id,
            source_image_id=method.source_image_id,
            source_token_ids=method.source_token_ids,
            ocr_confidence_source="synthetic-ocr-source",
            context_builder_id=self.CONTEXT_BUILDER,
            context_builder_version="test-v1",
            required_content=observations[UpstreamSignalV0.REQUIRED_CONTENT],
            parse_type=observations[UpstreamSignalV0.PARSE_TYPE],
            line_association=observations[UpstreamSignalV0.LINE_ASSOCIATION],
            arithmetic=observations[UpstreamSignalV0.ARITHMETIC],
        )
        return detect_suspicion(method, context, self.configuration(method))

    def bundle(
        self,
        *,
        suspicious: bool = True,
        seeds: tuple[B3CompatibleSeedV1, ...] | None = None,
    ) -> tuple[ProposedAdapterResultV1, MethodReadyFieldV1, SuspicionResultV0]:
        adapter, method = self.base_adapter()
        if seeds is None:
            seeds = ()
        adapter, method = self.adapter_with_seeds(adapter, method, seeds)
        return adapter, method, self.suspicion(method, suspicious=suspicious)

    def test_exact_original_c0_is_retained_without_normalization(self) -> None:
        adapter, method, suspicion = self.bundle()

        result = generate_candidate_drafts(
            suspicion_result=suspicion,
            adapter_result=adapter,
        )

        self.assertIs(result.original.method_ready_field, method)
        self.assertEqual(method.c0_candidate_id, result.original.c0_candidate_id)
        self.assertEqual("ＰＡＮＴＲＹ MART", result.original.value)
        self.assertEqual(method.original_value, result.original.value)
        self.assertEqual(method.source_token_ids, result.original.source_token_ids)

    def test_no_suspicion_with_and_without_seeds_emits_only_c0(self) -> None:
        adapter, method = self.base_adapter()
        span = self.valid_span(adapter)
        seed = self.seed(
            method,
            suffix="unused",
            source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
            proposed_value="PANTRY MART",
            spans=(span,),
        )
        for seeds in ((), (seed,)):
            with self.subTest(seed_count=len(seeds)):
                current_adapter, current_method = self.adapter_with_seeds(
                    adapter, method, seeds
                )
                suspicion = self.suspicion(current_method, suspicious=False)
                result = generate_candidate_drafts(
                    suspicion_result=suspicion,
                    adapter_result=current_adapter,
                )
                self.assertFalse(result.suspicion_result.is_suspicious)
                self.assertEqual((), result.altered_proposals)
                self.assertTrue(
                    all(
                        status.status
                        is CandidateSourceEvaluationStatusV0.NOT_EVALUATED_NO_SUSPICION
                        for status in result.source_statuses
                    )
                )

    def test_source_priority_and_adapter_order_are_deterministic(self) -> None:
        adapter, method = self.base_adapter()
        span = self.valid_span(adapter)
        seeds = (
            self.seed(
                method,
                suffix="generic-1",
                source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                proposed_value="pantry mart generic one",
            ),
            self.seed(
                method,
                suffix="source-1",
                source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                proposed_value="PANTRY MART SOURCE ONE",
                spans=(span,),
            ),
            self.seed(
                method,
                suffix="generic-2",
                source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                proposed_value="pantry mart generic two",
            ),
            self.seed(
                method,
                suffix="source-2",
                source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                proposed_value="PANTRY MART SOURCE TWO",
                spans=(span,),
            ),
        )
        adapter, method = self.adapter_with_seeds(adapter, method, seeds)

        result = generate_candidate_drafts(
            suspicion_result=self.suspicion(method, suspicious=True),
            adapter_result=adapter,
        )

        self.assertEqual(
            ("source-1", "source-2", "generic-1", "generic-2"),
            tuple(item.proposal_reference.rsplit(":", 1)[-1] for item in result.altered_proposals),
        )
        self.assertEqual(
            (1, 3, 0, 2),
            tuple(item.adapter_seed_position for item in result.altered_proposals),
        )

    def test_wrong_seed_identity_components_are_rejected(self) -> None:
        adapter, method = self.base_adapter()
        seed = self.seed(
            method,
            suffix="identity",
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            proposed_value="pantry mart",
        )
        adapter, method = self.adapter_with_seeds(adapter, method, (seed,))
        suspicion = self.suspicion(method, suspicious=True)
        mutations = (
            {"receipt_id": "another-receipt"},
            {"field_id": "another-field"},
            {"c0_candidate_id": "another-c0"},
            {"c0_value": "ANOTHER ORIGINAL"},
            {"b3_ruleset_id": "another-b3-ruleset"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                forged = deepcopy(adapter)
                altered = replace(seed, **mutation)
                object.__setattr__(
                    forged,
                    "b3_seeds",
                    tuple(
                        altered if item.seed_id == seed.seed_id else item
                        for item in forged.b3_seeds
                    ),
                )
                with self.assertRaises(CandidateGenerationIntegrityError):
                    generate_candidate_drafts(
                        suspicion_result=suspicion,
                        adapter_result=forged,
                    )

    def test_unknown_duplicate_missing_and_extraneous_seed_references_fail(self) -> None:
        adapter, method = self.base_adapter()
        seed = self.seed(
            method,
            suffix="references",
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            proposed_value="pantry mart",
        )
        adapter, method = self.adapter_with_seeds(adapter, method, (seed,))

        unknown_method = replace(method, b3_seed_ids=("unknown-seed",))
        unknown_adapter = replace(
            adapter,
            method_ready_fields=tuple(
                unknown_method if item.field_id == method.field_id else item
                for item in adapter.method_ready_fields
            ),
        )
        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(unknown_method, suspicious=True),
                adapter_result=unknown_adapter,
            )

        duplicate_adapter = deepcopy(adapter)
        object.__setattr__(
            duplicate_adapter,
            "b3_seeds",
            (seed, seed)
            + tuple(item for item in adapter.b3_seeds if item.seed_id != seed.seed_id),
        )
        with self.assertRaises(ValueError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(method, suspicious=True),
                adapter_result=duplicate_adapter,
            )

        missing_adapter = deepcopy(adapter)
        object.__setattr__(
            missing_adapter,
            "b3_seeds",
            tuple(item for item in adapter.b3_seeds if item.seed_id != seed.seed_id),
        )
        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(method, suspicious=True),
                adapter_result=missing_adapter,
            )

        undeclared_adapter, undeclared_method = self.adapter_with_seeds(
            adapter,
            method,
            (seed,),
            declared_ids=(),
        )
        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(undeclared_method, suspicious=True),
                adapter_result=undeclared_adapter,
            )

    def test_mismatched_suspicion_and_adapter_method_records_fail(self) -> None:
        adapter, method, _ = self.bundle()
        different = replace(method, method_field_id=f"{method.method_field_id}:different")
        suspicion = self.suspicion(different, suspicious=True)

        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=suspicion,
                adapter_result=adapter,
            )

    def test_method_source_image_must_match_original_b2_evidence(self) -> None:
        adapter, method = self.base_adapter()
        contradictory = replace(method, source_image_id="different-source-image")
        adapter = self.adapter_with_method(adapter, method, contradictory)

        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(contradictory, suspicious=True),
                adapter_result=adapter,
            )

    def test_method_processing_status_must_match_original_b2_evidence(self) -> None:
        adapter, method = self.base_adapter()
        for inconsistent in (SourceProcessingStatus.OCR_PARTIAL, None):
            with self.subTest(inconsistent=inconsistent):
                contradictory = replace(
                    method,
                    source_processing_status=inconsistent,
                )
                current_adapter = self.adapter_with_method(
                    adapter, method, contradictory
                )
                with self.assertRaises(CandidateGenerationIntegrityError):
                    generate_candidate_drafts(
                        suspicion_result=self.suspicion(
                            contradictory, suspicious=True
                        ),
                        adapter_result=current_adapter,
                    )

    def test_method_extraction_status_must_match_original_b2_output(self) -> None:
        adapter, method = self.base_adapter()
        for inconsistent in (ReceiptExtractionStatus.FAILED, None):
            with self.subTest(inconsistent=inconsistent):
                contradictory = replace(
                    method,
                    b2_extraction_status=inconsistent,
                )
                current_adapter = self.adapter_with_method(
                    adapter, method, contradictory
                )
                with self.assertRaises(CandidateGenerationIntegrityError):
                    generate_candidate_drafts(
                        suspicion_result=self.suspicion(
                            contradictory, suspicious=True
                        ),
                        adapter_result=current_adapter,
                    )

    def test_method_extractor_version_must_match_original_b2_output(self) -> None:
        adapter, method = self.base_adapter()
        contradictory = replace(
            method,
            b2_extractor_version="different-b2-extractor-version",
        )
        adapter = self.adapter_with_method(adapter, method, contradictory)

        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(contradictory, suspicious=True),
                adapter_result=adapter,
            )

    def test_adapter_extraction_status_must_match_original_b2_output(self) -> None:
        adapter, method = self.base_adapter()
        contradictory = replace(
            adapter,
            b2_extraction_status=ReceiptExtractionStatus.FAILED,
        )
        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(method, suspicious=True),
                adapter_result=contradictory,
            )

        missing = deepcopy(adapter)
        object.__setattr__(missing, "b2_extraction_status", None)
        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(method, suspicious=True),
                adapter_result=missing,
            )

    def test_selected_method_field_cannot_also_be_adapter_excluded(self) -> None:
        adapter, method = self.base_adapter()
        contradictory = replace(
            adapter,
            excluded_b2_field_ids=adapter.excluded_b2_field_ids + (method.field_id,),
        )

        with self.assertRaises(CandidateGenerationIntegrityError):
            generate_candidate_drafts(
                suspicion_result=self.suspicion(method, suspicious=True),
                adapter_result=contradictory,
            )

    def test_valid_literal_source_span_uses_original_ocr_text(self) -> None:
        adapter, method = self.base_adapter()
        token = self.store_token(adapter)
        span = self.valid_span(adapter, start=0, end=len(token.original_text))
        seed = self.seed(
            method,
            suffix="literal",
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            proposed_value="pantry mart",
            spans=(span,),
        )
        adapter, method = self.adapter_with_seeds(adapter, method, (seed,))

        result = generate_candidate_drafts(
            suspicion_result=self.suspicion(method, suspicious=True),
            adapter_result=adapter,
        )

        self.assertEqual("pantry mart", result.altered_proposals[0].proposed_value)
        self.assertEqual(token.original_text, result.altered_proposals[0].source_spans[0].text)
        self.assertNotEqual(
            result.altered_proposals[0].proposed_value,
            result.altered_proposals[0].source_spans[0].text,
        )

    def test_unknown_token_bad_offsets_and_wrong_slice_text_are_rejected(self) -> None:
        adapter, method = self.base_adapter()
        token = self.store_token(adapter)
        bad_spans = (
            SourceCharacterSpanV1(token_id="unknown-token", start=0, end=1, text="X"),
            SourceCharacterSpanV1(
                token_id=token.token_id,
                start=0,
                end=len(token.original_text) + 1,
                text="X" * (len(token.original_text) + 1),
            ),
            SourceCharacterSpanV1(
                token_id=token.token_id,
                start=0,
                end=3,
                text="XYZ",
            ),
        )
        for index, span in enumerate(bad_spans):
            with self.subTest(index=index):
                seed = self.seed(
                    method,
                    suffix=f"bad-span-{index}",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value=f"candidate-{index}",
                    spans=(span,),
                )
                current_adapter, current_method = self.adapter_with_seeds(
                    adapter, method, (seed,)
                )
                with self.assertRaises(CandidateGenerationIntegrityError):
                    generate_candidate_drafts(
                        suspicion_result=self.suspicion(
                            current_method, suspicious=True
                        ),
                        adapter_result=current_adapter,
                    )

    def test_composite_event_rule_and_absent_span_provenance_are_preserved(self) -> None:
        adapter, method = self.base_adapter()
        seed = self.seed(
            method,
            suffix="composite",
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            proposed_value="pantry mart",
            event_ids=("event:one", "event:two"),
            rule_ids=("rule:one", "rule:two"),
        )
        adapter, method = self.adapter_with_seeds(adapter, method, (seed,))

        result = generate_candidate_drafts(
            suspicion_result=self.suspicion(method, suspicious=True),
            adapter_result=adapter,
        )
        proposal = result.altered_proposals[0]

        self.assertIs(seed, proposal.b3_seed)
        self.assertEqual(seed.b3_event_ids, proposal.b3_event_ids)
        self.assertEqual(seed.b3_rule_ids, proposal.b3_rule_ids)
        self.assertEqual((), proposal.source_spans)

    def test_duplicate_raw_values_remain_separate_source_bound_proposals(self) -> None:
        adapter, method = self.base_adapter()
        seeds = tuple(
            self.seed(
                method,
                suffix=f"duplicate-{index}",
                source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                proposed_value="pantry mart",
            )
            for index in range(2)
        )
        adapter, method = self.adapter_with_seeds(adapter, method, seeds)

        result = generate_candidate_drafts(
            suspicion_result=self.suspicion(method, suspicious=True),
            adapter_result=adapter,
        )

        self.assertEqual(2, len(result.altered_proposals))
        self.assertEqual(
            ("pantry mart", "pantry mart"),
            tuple(item.proposed_value for item in result.altered_proposals),
        )
        self.assertNotEqual(
            result.altered_proposals[0].proposal_reference,
            result.altered_proposals[1].proposal_reference,
        )

    def test_unsupported_resource_sources_are_explicitly_unavailable(self) -> None:
        adapter, method, suspicion = self.bundle()
        result = generate_candidate_drafts(
            suspicion_result=suspicion,
            adapter_result=adapter,
        )
        statuses = {item.source_kind: item for item in result.source_statuses}

        for source_kind in (
            CandidateSourceKind.RETAILER_MAPPING,
            CandidateSourceKind.PANTRY_TERMINOLOGY,
        ):
            self.assertEqual(
                CandidateSourceEvaluationStatusV0.UNAVAILABLE_NOT_CONFIGURED,
                statuses[source_kind].status,
            )
            self.assertEqual((), statuses[source_kind].proposal_references)
            self.assertIsNotNone(statuses[source_kind].reason)

    def test_api_has_no_price_or_future_candidate_processing_inputs(self) -> None:
        signature = inspect.signature(generate_candidate_drafts)
        self.assertEqual(
            ("suspicion_result", "adapter_result"),
            tuple(signature.parameters),
        )
        adapter, _, suspicion = self.bundle()
        with self.assertRaises(TypeError):
            generate_candidate_drafts(
                suspicion_result=suspicion,
                adapter_result=adapter,
                price_evidence="forbidden",
            )

    def test_output_has_no_candidate_record_rank_or_limit_state(self) -> None:
        adapter, method = self.base_adapter()
        seed = self.seed(
            method,
            suffix="boundary",
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            proposed_value="pantry mart",
        )
        adapter, method = self.adapter_with_seeds(adapter, method, (seed,))
        result = generate_candidate_drafts(
            suspicion_result=self.suspicion(method, suspicious=True),
            adapter_result=adapter,
        )

        self.assertFalse(
            any(isinstance(item, CandidateRecordV1) for item in result.altered_proposals)
        )
        proposal_fields = {item.name for item in fields(AlteredCandidateProposalV0)}
        self.assertTrue(
            {"candidate_id", "normalized_dedup_key", "preliminary_rank", "limit_status"}
            .isdisjoint(proposal_fields)
        )

    def test_repeated_calls_are_identical_and_do_not_mutate_upstream(self) -> None:
        adapter, method = self.base_adapter()
        seed = self.seed(
            method,
            suffix="deterministic",
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            proposed_value="pantry mart",
        )
        adapter, method = self.adapter_with_seeds(adapter, method, (seed,))
        suspicion = self.suspicion(method, suspicious=True)
        adapter_before = deepcopy(adapter)
        suspicion_before = deepcopy(suspicion)

        first = generate_candidate_drafts(
            suspicion_result=suspicion,
            adapter_result=adapter,
        )
        second = generate_candidate_drafts(
            suspicion_result=suspicion,
            adapter_result=adapter,
        )

        self.assertEqual(first, second)
        self.assertEqual(adapter_before, adapter)
        self.assertEqual(suspicion_before, suspicion)
        with self.assertRaises(FrozenInstanceError):
            first.original.value = "changed"  # type: ignore[misc]

    def test_result_reconstruction_cannot_forge_proposals_or_source_status(self) -> None:
        adapter, method = self.base_adapter()
        seed = self.seed(
            method,
            suffix="result-integrity",
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            proposed_value="pantry mart",
        )
        adapter, method = self.adapter_with_seeds(adapter, method, (seed,))
        result = generate_candidate_drafts(
            suspicion_result=self.suspicion(method, suspicious=True),
            adapter_result=adapter,
        )

        with self.assertRaises(ValueError):
            replace(result, altered_proposals=())
        forged_status = replace(
            result.source_statuses[0],
            status=CandidateSourceEvaluationStatusV0.UNAVAILABLE_NOT_CONFIGURED,
            proposal_references=(),
            reason="Forged unavailable source.",
        )
        with self.assertRaises(ValueError):
            replace(result, source_statuses=(forged_status,) + result.source_statuses[1:])

    def test_candidate_generation_does_not_invoke_b3_processing(self) -> None:
        adapter, _, suspicion = self.bundle()
        with patch(
            "pipeline.baseline_b3.apply_b3",
            side_effect=AssertionError("candidate generation must not invoke B3"),
        ):
            result = generate_candidate_drafts(
                suspicion_result=suspicion,
                adapter_result=adapter,
            )
        self.assertIsInstance(result, CandidateGenerationResultV0)

    def test_local_record_types_are_frozen_slotted_and_not_exported_via_package(self) -> None:
        adapter, _, suspicion = self.bundle()
        result = generate_candidate_drafts(
            suspicion_result=suspicion,
            adapter_result=adapter,
        )
        self.assertIsInstance(result.original, OriginalCandidateDraftV0)
        self.assertTrue(
            all(isinstance(item, CandidateSourceStatusV0) for item in result.source_statuses)
        )
        self.assertFalse(hasattr(result, "__dict__"))


if __name__ == "__main__":
    unittest.main()
