"""Synthetic adversarial tests for deterministic suspicion detector V0."""

from __future__ import annotations

import inspect
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal

from pipeline.contracts import (
    FieldStatus,
    OcrSourceToken,
    Point,
    ReceiptExtractionStatus,
    ReceiptFieldName,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    StructuredField,
)
from pipeline.proposed.contracts import (
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    MethodReadyFieldV1,
)
from pipeline.proposed.suspicion import (
    ConfidenceAggregationV0,
    ConfidenceAvailabilityV0,
    ConfidenceEvidenceV0,
    ConfidenceRuleV0,
    SUSPICION_REASON_ORDER,
    SuspicionConfigurationV0,
    SuspicionContextV0,
    SuspicionIntegrityError,
    SuspicionReasonCode,
    SuspicionResultV0,
    UpstreamObservationStateV0,
    UpstreamObservationV0,
    UpstreamSignalV0,
    detect_suspicion,
)


class ProposedSuspicionTests(unittest.TestCase):
    RECEIPT_ID = "suspicion-receipt"
    FIELD_ID = f"{RECEIPT_ID}:b2:store-name"
    METHOD_FIELD_ID = f"{FIELD_ID}:method:v1"
    OCR_SOURCE = "paddleocr-3.7-en-cpu"
    B2_SOURCE = "B2-layout-graph-v0"
    CONTEXT_BUILDER = "synthetic-context-builder"

    def gate(self) -> SourceEvidenceGateResult:
        return SourceEvidenceGateResult(
            gate_result_id=f"{self.RECEIPT_ID}:gate",
            receipt_id=self.RECEIPT_ID,
            decision=SourceEvidenceDecision.SUFFICIENT,
        )

    def token(self, token_id: str, confidence: float | None) -> OcrSourceToken:
        return OcrSourceToken(
            receipt_id=self.RECEIPT_ID,
            token_id=token_id,
            original_text=token_id.upper(),
            polygon=(Point(0, 0), Point(10, 0), Point(10, 5), Point(0, 5)),
            raw_confidence=confidence,
        )

    def method_field(
        self,
        *,
        ocr_confidences: tuple[float | None, ...] = (0.9, 0.8),
        extractor_confidence: float | None = 0.75,
    ) -> MethodReadyFieldV1:
        tokens = tuple(
            self.token(f"source-token-{index}", confidence)
            for index, confidence in enumerate(ocr_confidences)
        )
        token_ids = tuple(token.token_id for token in tokens)
        field = StructuredField(
            field_id=self.FIELD_ID,
            receipt_id=self.RECEIPT_ID,
            field_name=ReceiptFieldName.STORE_NAME,
            status=FieldStatus.EXTRACTED,
            value="PANTRY MART",
            source_token_ids=token_ids,
            confidence=extractor_confidence,
        )
        return MethodReadyFieldV1(
            method_field_id=self.METHOD_FIELD_ID,
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_name=ReceiptFieldName.STORE_NAME,
            original_b2_field=field,
            original_value="PANTRY MART",
            c0_candidate_id=f"{self.FIELD_ID}:c0",
            c0_value="PANTRY MART",
            source_token_ids=token_ids,
            source_tokens=tokens,
            source_image_id="synthetic-image",
            source_processing_status=SourceProcessingStatus.OCR_COMPLETED,
            b2_extraction_status=ReceiptExtractionStatus.EXTRACTED,
            b2_extractor_version=self.B2_SOURCE,
            stored_gate_result=self.gate(),
        )

    def theta_ref(
        self,
        *,
        kind: ConfigurationKind = ConfigurationKind.THETA_A,
        state: ConfigurationState = ConfigurationState.READY,
        configuration_id: str = "theta-a-synthetic-test",
    ) -> ConfigurationRefV1:
        return ConfigurationRefV1(
            kind=kind,
            configuration_id=configuration_id,
            configuration_version="test-v1",
            state=state,
            content_hash="sha256:synthetic-test-only"
            if state is ConfigurationState.READY
            else None,
            status_reason=None
            if state is ConfigurationState.READY
            else "Synthetic configuration is not ready.",
        )

    def rule(
        self,
        *,
        rule_id: str,
        source: str,
        aggregation: ConfidenceAggregationV0,
        threshold: str = "0.50",
        minimum: str = "0.00",
        maximum: str = "1.00",
    ) -> ConfidenceRuleV0:
        return ConfidenceRuleV0(
            rule_id=rule_id,
            score_source=source,
            aggregation=aggregation,
            threshold=Decimal(threshold),
            domain_minimum=Decimal(minimum),
            domain_maximum=Decimal(maximum),
        )

    def configuration(
        self,
        *,
        theta_ref: ConfigurationRefV1 | None = None,
        ocr_source: str | None = None,
        extractor_source: str | None = None,
        threshold: str = "0.50",
    ) -> SuspicionConfigurationV0:
        return SuspicionConfigurationV0(
            theta_a_ref=theta_ref or self.theta_ref(),
            ocr_confidence_rule=self.rule(
                rule_id="ocr-confidence-test-rule",
                source=ocr_source or self.OCR_SOURCE,
                aggregation=ConfidenceAggregationV0.MIN_ALL_REFERENCED,
                threshold=threshold,
            ),
            extractor_confidence_rule=self.rule(
                rule_id="extractor-confidence-test-rule",
                source=extractor_source or self.B2_SOURCE,
                aggregation=ConfidenceAggregationV0.DIRECT,
                threshold=threshold,
            ),
            context_builder_id=self.CONTEXT_BUILDER,
            context_builder_version="test-v1",
        )

    def observation(
        self,
        signal: UpstreamSignalV0,
        state: UpstreamObservationStateV0 = UpstreamObservationStateV0.PASS,
        *,
        receipt_id: str | None = None,
        field_id: str | None = None,
        evidence_ids: tuple[str, ...] | None = None,
    ) -> UpstreamObservationV0:
        if evidence_ids is None:
            evidence_ids = (
                (f"{signal.value.lower()}:synthetic-evidence",)
                if state in (
                    UpstreamObservationStateV0.PASS,
                    UpstreamObservationStateV0.FAIL,
                )
                else ()
            )
        reason = (
            None
            if state is UpstreamObservationStateV0.PASS
            else f"Synthetic {signal.value} {state.value.lower()} reason."
        )
        return UpstreamObservationV0(
            observation_id=f"observation:{signal.value.lower()}",
            receipt_id=receipt_id or self.RECEIPT_ID,
            field_id=field_id or self.FIELD_ID,
            signal=signal,
            state=state,
            provider_id=self.CONTEXT_BUILDER,
            provider_version="test-v1",
            evidence_ids=evidence_ids,
            reason=reason,
        )

    def context(
        self,
        method_field: MethodReadyFieldV1,
        *,
        states: dict[UpstreamSignalV0, UpstreamObservationStateV0] | None = None,
        ocr_source: str | None = None,
        method_field_id: str | None = None,
        field_id: str | None = None,
        source_token_ids: tuple[str, ...] | None = None,
    ) -> SuspicionContextV0:
        states = states or {}
        observations = {
            signal: self.observation(signal, states.get(signal, UpstreamObservationStateV0.PASS))
            for signal in UpstreamSignalV0
        }
        return SuspicionContextV0(
            context_id=f"{method_field.method_field_id}:synthetic-context",
            receipt_id=method_field.receipt_id,
            method_field_id=method_field_id or method_field.method_field_id,
            field_id=field_id or method_field.field_id,
            gate_result_id=method_field.stored_gate_result.gate_result_id,
            source_image_id=method_field.source_image_id,
            source_token_ids=source_token_ids or method_field.source_token_ids,
            ocr_confidence_source=ocr_source or self.OCR_SOURCE,
            context_builder_id=self.CONTEXT_BUILDER,
            context_builder_version="test-v1",
            required_content=observations[UpstreamSignalV0.REQUIRED_CONTENT],
            parse_type=observations[UpstreamSignalV0.PARSE_TYPE],
            line_association=observations[UpstreamSignalV0.LINE_ASSOCIATION],
            arithmetic=observations[UpstreamSignalV0.ARITHMETIC],
        )

    def detect(
        self,
        method_field: MethodReadyFieldV1 | None = None,
        *,
        context: SuspicionContextV0 | None = None,
        configuration: SuspicionConfigurationV0 | None = None,
    ) -> SuspicionResultV0:
        method_field = method_field or self.method_field()
        return detect_suspicion(
            method_field,
            context or self.context(method_field),
            configuration or self.configuration(),
        )

    def test_valid_extracted_field_has_no_suspicion_and_retains_c0(self) -> None:
        method = self.method_field()
        result = self.detect(method)

        self.assertFalse(result.is_suspicious)
        self.assertEqual((), result.reasons)
        self.assertIs(method, result.method_ready_field)
        self.assertEqual(method.original_value, result.method_ready_field.c0_value)

    def test_each_of_six_reasons_triggers_independently(self) -> None:
        cases = (
            (
                SuspicionReasonCode.LOW_OCR_CONFIDENCE,
                self.method_field(ocr_confidences=(0.49, 0.8)),
                None,
            ),
            (
                SuspicionReasonCode.LOW_EXTRACTOR_CONFIDENCE,
                self.method_field(extractor_confidence=0.49),
                None,
            ),
            (
                SuspicionReasonCode.MISSING_REQUIRED_CONTENT,
                self.method_field(),
                UpstreamSignalV0.REQUIRED_CONTENT,
            ),
            (
                SuspicionReasonCode.PARSE_TYPE_FAILURE,
                self.method_field(),
                UpstreamSignalV0.PARSE_TYPE,
            ),
            (
                SuspicionReasonCode.LINE_ASSOCIATION_CONFLICT,
                self.method_field(),
                UpstreamSignalV0.LINE_ASSOCIATION,
            ),
            (
                SuspicionReasonCode.ARITHMETIC_CONTRADICTION,
                self.method_field(),
                UpstreamSignalV0.ARITHMETIC,
            ),
        )
        for expected, method, signal in cases:
            with self.subTest(reason=expected):
                states = (
                    {signal: UpstreamObservationStateV0.FAIL}
                    if signal is not None
                    else None
                )
                result = self.detect(method, context=self.context(method, states=states))
                self.assertEqual((expected,), result.reasons)
                self.assertTrue(result.is_suspicious)

    def test_multiple_reasons_always_use_canonical_order(self) -> None:
        method = self.method_field(
            ocr_confidences=(0.2, 0.9), extractor_confidence=0.3
        )
        states = {signal: UpstreamObservationStateV0.FAIL for signal in UpstreamSignalV0}

        result = self.detect(method, context=self.context(method, states=states))

        self.assertEqual(SUSPICION_REASON_ORDER, result.reasons)

    def test_repeated_calls_are_deterministic(self) -> None:
        method = self.method_field(ocr_confidences=(0.7, 0.4))
        context = self.context(method)
        configuration = self.configuration()

        first = self.detect(method, context=context, configuration=configuration)
        second = self.detect(method, context=context, configuration=configuration)

        self.assertEqual(first, second)
        self.assertEqual(first.result_id, second.result_id)

    def test_valid_result_reconstruction_passes_complete_integrity_checks(self) -> None:
        original = self.detect()

        reconstructed = replace(original)

        self.assertEqual(original, reconstructed)

    def test_fabricated_ocr_values_and_matching_reason_are_rejected(self) -> None:
        original = self.detect()
        fabricated_evidence = tuple(
            replace(item, value=Decimal("0.10"))
            for item in original.ocr_confidence.evidence
        )
        fabricated = replace(
            original.ocr_confidence,
            evidence=fabricated_evidence,
            aggregate=Decimal("0.10"),
        )

        with self.assertRaisesRegex(ValueError, "original source-token confidence"):
            replace(
                original,
                ocr_confidence=fabricated,
                reasons=(SuspicionReasonCode.LOW_OCR_CONFIDENCE,),
            )

    def test_wrong_ocr_score_source_is_rejected_with_matching_rule_id(self) -> None:
        original = self.detect()
        fabricated = replace(
            original.ocr_confidence,
            score_source="unrelated-ocr-score-source",
        )

        self.assertEqual(
            original.ocr_confidence.rule_id,
            fabricated.rule_id,
        )
        with self.assertRaisesRegex(ValueError, "original source-token confidence"):
            replace(original, ocr_confidence=fabricated)

    def test_wrong_extractor_confidence_observation_is_rejected(self) -> None:
        original = self.detect()
        fabricated = replace(
            original.extractor_confidence,
            evidence=(
                ConfidenceEvidenceV0(
                    evidence_id=self.FIELD_ID,
                    value=Decimal("0.10"),
                ),
            ),
            aggregate=Decimal("0.10"),
        )

        with self.assertRaisesRegex(ValueError, "original B2 confidence"):
            replace(
                original,
                extractor_confidence=fabricated,
                reasons=(SuspicionReasonCode.LOW_EXTRACTOR_CONFIDENCE,),
            )

    def test_incorrect_observation_aggregation_is_rejected(self) -> None:
        method = self.method_field(ocr_confidences=(0.8,))
        original = self.detect(method)
        fabricated = replace(
            original.ocr_confidence,
            aggregation=ConfidenceAggregationV0.DIRECT,
        )

        with self.assertRaisesRegex(ValueError, "original source-token confidence"):
            replace(original, ocr_confidence=fabricated)

    def test_availability_inconsistent_with_original_evidence_is_rejected(self) -> None:
        method = self.method_field(ocr_confidences=(None,))
        original = self.detect(method)
        self.assertEqual(
            ConfidenceAvailabilityV0.UNAVAILABLE,
            original.ocr_confidence.availability,
        )
        fabricated = replace(
            original.ocr_confidence,
            availability=ConfidenceAvailabilityV0.AVAILABLE,
            evidence=(
                ConfidenceEvidenceV0(
                    evidence_id="source-token-0",
                    value=Decimal("0.80"),
                ),
            ),
            aggregate=Decimal("0.80"),
            missing_evidence_ids=(),
        )

        with self.assertRaisesRegex(ValueError, "original source-token confidence"):
            replace(original, ocr_confidence=fabricated)

    def test_single_and_multiple_token_minimum_aggregation(self) -> None:
        single = self.detect(self.method_field(ocr_confidences=(0.8,)))
        multiple = self.detect(self.method_field(ocr_confidences=(0.9, 0.6, 0.7)))

        self.assertEqual(Decimal("0.8"), single.ocr_confidence.aggregate)
        self.assertEqual(Decimal("0.6"), multiple.ocr_confidence.aggregate)
        self.assertEqual(
            ConfidenceAggregationV0.MIN_ALL_REFERENCED,
            multiple.ocr_confidence.aggregation,
        )

    def test_any_missing_ocr_score_makes_complete_aggregate_unavailable(self) -> None:
        for confidences, expected_missing in (
            ((0.9, None), ("source-token-1",)),
            ((None, None), ("source-token-0", "source-token-1")),
        ):
            with self.subTest(confidences=confidences):
                result = self.detect(self.method_field(ocr_confidences=confidences))
                self.assertEqual(
                    ConfidenceAvailabilityV0.UNAVAILABLE,
                    result.ocr_confidence.availability,
                )
                self.assertIsNone(result.ocr_confidence.aggregate)
                self.assertEqual(expected_missing, result.ocr_confidence.missing_evidence_ids)
                self.assertNotIn(SuspicionReasonCode.LOW_OCR_CONFIDENCE, result.reasons)
                self.assertEqual(len(confidences), len(result.ocr_confidence.evidence))

    def test_missing_extractor_confidence_is_unavailable_not_low(self) -> None:
        result = self.detect(self.method_field(extractor_confidence=None))

        self.assertEqual(
            ConfidenceAvailabilityV0.UNAVAILABLE,
            result.extractor_confidence.availability,
        )
        self.assertIsNone(result.extractor_confidence.aggregate)
        self.assertNotIn(SuspicionReasonCode.LOW_EXTRACTOR_CONFIDENCE, result.reasons)

    def test_strict_threshold_comparison_below_equal_and_above(self) -> None:
        for value, expected in ((0.49, True), (0.50, False), (0.51, False)):
            with self.subTest(value=value):
                method = self.method_field(ocr_confidences=(value,))
                result = self.detect(method)
                self.assertEqual(
                    expected,
                    SuspicionReasonCode.LOW_OCR_CONFIDENCE in result.reasons,
                )

    def test_declared_domains_are_strictly_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "minimum"):
            self.rule(
                rule_id="bad-domain",
                source=self.OCR_SOURCE,
                aggregation=ConfidenceAggregationV0.MIN_ALL_REFERENCED,
                minimum="1",
                maximum="0",
            )
        with self.assertRaisesRegex(ValueError, "threshold"):
            self.rule(
                rule_id="bad-threshold",
                source=self.OCR_SOURCE,
                aggregation=ConfidenceAggregationV0.MIN_ALL_REFERENCED,
                threshold="2",
            )
        with self.assertRaisesRegex(SuspicionIntegrityError, "declared domain"):
            self.detect(self.method_field(ocr_confidences=(1.1,)))

    def test_nonfinite_boolean_and_nonnumeric_scores_are_rejected(self) -> None:
        for invalid in (float("nan"), float("inf"), float("-inf"), True, "0.4"):
            with self.subTest(value=invalid):
                method = self.method_field(ocr_confidences=(0.8,))
                object.__setattr__(method.source_tokens[0], "raw_confidence", invalid)
                with self.assertRaises(SuspicionIntegrityError):
                    self.detect(method)

    def test_confidence_sources_and_context_builder_must_match(self) -> None:
        method = self.method_field()
        with self.assertRaisesRegex(SuspicionIntegrityError, "OCR confidence source"):
            self.detect(method, context=self.context(method, ocr_source="another-engine"))
        with self.assertRaisesRegex(SuspicionIntegrityError, "Extractor confidence source"):
            self.detect(
                method,
                configuration=self.configuration(extractor_source="another-b2"),
            )
        context = self.context(method)
        object.__setattr__(context, "context_builder_version", "another-version")
        with self.assertRaisesRegex(SuspicionIntegrityError, "Context builder"):
            self.detect(method, context=context)

    def test_theta_a_kind_state_and_result_reference_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "THETA_A"):
            self.configuration(theta_ref=self.theta_ref(kind=ConfigurationKind.KAPPA))
        with self.assertRaisesRegex(ValueError, "READY"):
            self.configuration(
                theta_ref=self.theta_ref(state=ConfigurationState.NOT_READY)
            )

        result = self.detect()
        another_theta = self.theta_ref(configuration_id="different-theta-a")
        with self.assertRaisesRegex(ValueError, "exact Theta_A"):
            replace(result, theta_a_ref=another_theta)

    def test_receipt_field_method_gate_image_and_token_identity_are_checked(self) -> None:
        method = self.method_field()
        mutations = (
            ("receipt_id", "another-receipt", "receipt"),
            ("method_field_id", "another-method-field", "method field"),
            ("field_id", "another-field", "field"),
            ("gate_result_id", "another-gate", "gate result"),
            ("source_image_id", "another-image", "source image"),
            ("source_token_ids", ("another-token",), "source tokens"),
        )
        for attribute, value, message in mutations:
            with self.subTest(attribute=attribute):
                context = self.context(method)
                object.__setattr__(context, attribute, value)
                with self.assertRaisesRegex(SuspicionIntegrityError, message):
                    self.detect(method, context=context)

        object.__setattr__(method.source_tokens[0], "token_id", "corrupt-token")
        with self.assertRaisesRegex(SuspicionIntegrityError, "source-token order"):
            self.detect(method)

    def test_invalid_stored_gate_is_an_integrity_failure(self) -> None:
        method = self.method_field()
        object.__setattr__(
            method.stored_gate_result,
            "decision",
            SourceEvidenceDecision.INSUFFICIENT,
        )
        with self.assertRaisesRegex(SuspicionIntegrityError, "stored SUFFICIENT"):
            self.detect(method)

    def test_unavailable_and_not_applicable_observations_do_not_trigger(self) -> None:
        method = self.method_field(ocr_confidences=(None,), extractor_confidence=None)
        states = {
            UpstreamSignalV0.REQUIRED_CONTENT: UpstreamObservationStateV0.UNAVAILABLE,
            UpstreamSignalV0.PARSE_TYPE: UpstreamObservationStateV0.NOT_APPLICABLE,
            UpstreamSignalV0.LINE_ASSOCIATION: UpstreamObservationStateV0.UNAVAILABLE,
            UpstreamSignalV0.ARITHMETIC: UpstreamObservationStateV0.NOT_APPLICABLE,
        }

        result = self.detect(method, context=self.context(method, states=states))

        self.assertEqual((), result.reasons)
        self.assertFalse(result.is_suspicious)

    def test_observation_states_require_consistent_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "FAIL requires evidence"):
            self.observation(
                UpstreamSignalV0.PARSE_TYPE,
                UpstreamObservationStateV0.FAIL,
                evidence_ids=(),
            )
        with self.assertRaisesRegex(ValueError, "cannot claim evidence"):
            self.observation(
                UpstreamSignalV0.ARITHMETIC,
                UpstreamObservationStateV0.UNAVAILABLE,
                evidence_ids=("invented-evidence",),
            )
        method = self.method_field()
        context = self.context(method)
        mismatched = replace(context.parse_type, provider_version="another-version")
        with self.assertRaisesRegex(ValueError, "match the context builder"):
            replace(context, parse_type=mismatched)

    def test_triggered_observation_retains_all_provenance(self) -> None:
        method = self.method_field()
        context = self.context(
            method,
            states={
                UpstreamSignalV0.PARSE_TYPE: UpstreamObservationStateV0.FAIL
            },
        )
        parse = replace(
            context.parse_type,
            evidence_ids=("parse-evidence-a", "parse-evidence-b"),
        )
        context = replace(context, parse_type=parse)

        result = self.detect(method, context=context)

        self.assertIs(parse, result.context.parse_type)
        self.assertEqual(
            ("parse-evidence-a", "parse-evidence-b"),
            result.context.parse_type.evidence_ids,
        )

    def test_missing_or_unresolved_b2_field_cannot_become_method_ready(self) -> None:
        method = self.method_field()
        for status in (FieldStatus.MISSING, FieldStatus.UNRESOLVED):
            with self.subTest(status=status):
                empty = StructuredField(
                    field_id=self.FIELD_ID,
                    receipt_id=self.RECEIPT_ID,
                    field_name=ReceiptFieldName.STORE_NAME,
                    status=status,
                    unresolved_reason="Synthetic missing or unresolved field.",
                )
                with self.assertRaisesRegex(ValueError, "Only an EXTRACTED"):
                    replace(method, original_b2_field=empty)

    def test_records_are_frozen_and_source_evidence_is_unchanged(self) -> None:
        method = self.method_field()
        original_tokens = method.source_tokens
        context = self.context(method)
        result = self.detect(method, context=context)

        with self.assertRaises(FrozenInstanceError):
            result.reasons = ()
        with self.assertRaises(FrozenInstanceError):
            result.context.field_id = "changed"
        self.assertIs(original_tokens, method.source_tokens)
        self.assertEqual(
            tuple(token.raw_confidence for token in original_tokens),
            (0.9, 0.8),
        )

    def test_public_api_has_no_candidate_policy_or_ground_truth_inputs(self) -> None:
        signature = inspect.signature(detect_suspicion)
        self.assertEqual(
            ("method_field", "context", "configuration"),
            tuple(signature.parameters),
        )
        forbidden_fragments = (
            "candidate",
            "retailer",
            "price",
            "probability",
            "ground_truth",
            "phi",
            "pt1",
            "pt2",
            "review",
            "persistence",
        )
        public_field_names = {
            item.name
            for record in (
                SuspicionContextV0,
                SuspicionConfigurationV0,
                SuspicionResultV0,
            )
            for item in fields(record)
        }
        for fragment in forbidden_fragments:
            self.assertFalse(any(fragment in name.lower() for name in public_field_names))


if __name__ == "__main__":
    unittest.main()
