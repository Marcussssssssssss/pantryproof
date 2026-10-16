"""Synthetic invariant tests for proposed-system shared Contract V1."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, is_dataclass, replace
from decimal import Decimal

import pipeline.proposed.contracts as proposed_contracts
from pipeline.proposed.adapter import ProposedAdapterResultV1
from pipeline.contracts import (
    FailureStage,
    FieldStatus,
    OcrSourceToken,
    Point,
    PolicyState,
    PreResolutionDisposition,
    ReceiptExtractionStatus,
    ReceiptFieldName,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    StructuredField,
)
from pipeline.proposed.contracts import (
    AutomaticCommitPermission,
    CandidateAuditStatus,
    CandidateEvidenceV1,
    CandidateLimitStatus,
    CandidateProvenanceV1,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationRefsV1,
    ConfigurationState,
    ConstraintEligibility,
    ConstraintReasonCode,
    ConstraintResultV1,
    FEATURE_SCHEMA_ID_V1,
    FEATURE_SLOT_ORDER,
    FieldDecisionState,
    FieldDecisionV1,
    FinalApplicationOutcomeV1,
    MethodReadyFieldV1,
    PersistenceResultState,
    PreliminaryRankV1,
    ReviewResolutionKind,
    ReviewResolutionV1,
    SourceCharacterSpanV1,
    ValueAvailabilityStatus,
    to_deterministic_json,
)


class ProposedContractTests(unittest.TestCase):
    RECEIPT_ID = "contract-v1-receipt"
    FIELD_ID = "contract-v1-receipt:store-name"
    C0_ID = f"{FIELD_ID}:c0"

    def gate(self) -> SourceEvidenceGateResult:
        return SourceEvidenceGateResult(
            gate_result_id="contract-v1-gate",
            receipt_id=self.RECEIPT_ID,
            decision=SourceEvidenceDecision.SUFFICIENT,
        )

    def token(self) -> OcrSourceToken:
        return OcrSourceToken(
            receipt_id=self.RECEIPT_ID,
            token_id="store-token",
            original_text="PANTRY MART",
            polygon=(Point(0, 0), Point(10, 0), Point(10, 5), Point(0, 5)),
            raw_confidence=0.9,
        )

    def structured_field(self) -> StructuredField:
        return StructuredField(
            field_id=self.FIELD_ID,
            receipt_id=self.RECEIPT_ID,
            field_name=ReceiptFieldName.STORE_NAME,
            status=FieldStatus.EXTRACTED,
            value="PANTRY MART",
            source_token_ids=("store-token",),
            confidence=0.8,
        )

    def method_field(self) -> MethodReadyFieldV1:
        field = self.structured_field()
        return MethodReadyFieldV1(
            method_field_id=f"{self.FIELD_ID}:method:v1",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_name=ReceiptFieldName.STORE_NAME,
            original_b2_field=field,
            original_value="PANTRY MART",
            c0_candidate_id=self.C0_ID,
            c0_value="PANTRY MART",
            source_token_ids=("store-token",),
            source_tokens=(self.token(),),
            source_image_id="image-1",
            source_processing_status=SourceProcessingStatus.OCR_COMPLETED,
            b2_extraction_status=ReceiptExtractionStatus.EXTRACTED,
            b2_extractor_version="B2-layout-graph-v0",
            stored_gate_result=self.gate(),
        )

    def config_ref(
        self,
        kind: ConfigurationKind,
        state: ConfigurationState = ConfigurationState.READY,
    ) -> ConfigurationRefV1:
        return ConfigurationRefV1(
            kind=kind,
            configuration_id=f"{kind.value.lower()}-config",
            configuration_version="v1",
            state=state,
            content_hash=f"sha256:{kind.value.lower()}" if state is ConfigurationState.READY else None,
            status_reason=None if state is ConfigurationState.READY else "Not selected yet.",
        )

    def configs(self, *, ready: bool = True) -> ConfigurationRefsV1:
        state = ConfigurationState.READY if ready else ConfigurationState.NOT_READY
        return ConfigurationRefsV1(
            theta_a=self.config_ref(ConfigurationKind.THETA_A, state),
            kappa=self.config_ref(ConfigurationKind.KAPPA, state),
            phi=self.config_ref(ConfigurationKind.PHI, state),
            pt1=self.config_ref(ConfigurationKind.PT1, state),
            pt2=self.config_ref(ConfigurationKind.PT2, state),
        )

    def original_candidate(self) -> CandidateRecordV1:
        provenance = CandidateProvenanceV1(
            provenance_id="provenance-c0",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            candidate_id=self.C0_ID,
            source_kind=CandidateSourceKind.ORIGINAL,
            original_observed_value="PANTRY MART",
            source_token_ids=("store-token",),
            source_spans=(
                SourceCharacterSpanV1("store-token", 0, 11, "PANTRY MART"),
            ),
        )
        return CandidateRecordV1(
            candidate_id=self.C0_ID,
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            c0_candidate_id=self.C0_ID,
            value="PANTRY MART",
            normalized_dedup_key="pantry mart",
            role=CandidateRole.ORIGINAL,
            provenance=(provenance,),
            limit_status=CandidateLimitStatus.RETAINED,
        )

    def altered_candidate(
        self, *, limit_status: CandidateLimitStatus = CandidateLimitStatus.RETAINED
    ) -> CandidateRecordV1:
        candidate_id = f"{self.FIELD_ID}:candidate:001"
        provenance = CandidateProvenanceV1(
            provenance_id="provenance-generic",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            candidate_id=candidate_id,
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            original_observed_value="PANTRY MART",
            source_token_ids=("store-token",),
            source_spans=(
                SourceCharacterSpanV1("store-token", 0, 11, "PANTRY MART"),
            ),
            generic_rule_id="B3-TEXT-NORMALIZE",
        )
        return CandidateRecordV1(
            candidate_id=candidate_id,
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            c0_candidate_id=self.C0_ID,
            value="pantry mart",
            normalized_dedup_key="pantry mart",
            role=CandidateRole.ALTERED,
            provenance=(provenance,),
            limit_status=limit_status,
            preliminary_rank=PreliminaryRankV1(
                source_priority_rank=2,
                normalized_edit_similarity=Decimal("0.95"),
                source_order_displacement=0,
                normalized_candidate_text="pantry mart",
                rank_position=1,
            ),
            overflow_reason="LIMIT_OVERFLOW"
            if limit_status is CandidateLimitStatus.LIMIT_OVERFLOW
            else None,
        )

    def constraint(
        self,
        candidate: CandidateRecordV1,
        eligibility: ConstraintEligibility = ConstraintEligibility.ELIGIBLE,
    ) -> ConstraintResultV1:
        return ConstraintResultV1(
            constraint_result_id=f"{candidate.candidate_id}:constraints",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            candidate_id=candidate.candidate_id,
            eligibility=eligibility,
            evaluated_rule_ids=("TYPE-V1", "SOURCE-V1"),
            reason_codes=(ConstraintReasonCode.FIELD_TYPE_INVALID,)
            if eligibility is ConstraintEligibility.CONSTRAINT_REJECTED
            else (),
            reason_detail="Synthetic type rejection."
            if eligibility is ConstraintEligibility.CONSTRAINT_REJECTED
            else None,
        )

    def evidence(
        self,
        candidate: CandidateRecordV1 | None = None,
        configuration_refs: ConfigurationRefsV1 | None = None,
    ) -> CandidateEvidenceV1:
        candidate = candidate or self.altered_candidate()
        return CandidateEvidenceV1(
            evidence_id=f"{candidate.candidate_id}:evidence",
            candidate=candidate,
            constraint_result=self.constraint(candidate),
            candidate_status=CandidateAuditStatus.SCORING_ELIGIBLE,
            configuration_refs=configuration_refs or self.configs(),
            feature_schema_id=FEATURE_SCHEMA_ID_V1,
            feature_slots=FEATURE_SLOT_ORDER,
            feature_values=(
                Decimal("0.91"),
                None,
                Decimal("0.95"),
                "ALIGNED",
                None,
                True,
                None,
            ),
            feature_provenance_refs=(
                ("store-token",),
                (),
                ("provenance-generic",),
                ("layout:b2",),
                (),
                ("arithmetic:audit",),
                (),
            ),
            missingness_mask=(False, True, False, False, True, False, True),
            score_status=ValueAvailabilityStatus.AVAILABLE,
            raw_score=Decimal("2.125"),
            calibration_status=ValueAvailabilityStatus.AVAILABLE,
            probability_available=True,
            calibrated_probability=Decimal("0.8750"),
        )

    def decision(
        self,
        state: FieldDecisionState = FieldDecisionState.REVIEW_REQUIRED,
        *,
        candidate: CandidateRecordV1 | None = None,
        evidence: CandidateEvidenceV1 | None = None,
        method_ready_field: MethodReadyFieldV1 | None = None,
        configuration_refs: ConfigurationRefsV1 | None = None,
    ) -> FieldDecisionV1:
        if candidate is None:
            candidate = evidence.candidate if evidence is not None else self.altered_candidate()
        evidence = evidence or self.evidence(candidate)
        original = method_ready_field or self.method_field()
        configuration_refs = configuration_refs or evidence.configuration_refs
        return FieldDecisionV1(
            decision_id=f"{self.FIELD_ID}:decision",
            method_field_id=original.method_field_id,
            method_ready_field=original,
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            c0_candidate_id=original.c0_candidate_id,
            c0_value=original.c0_value,
            selected_candidate=candidate,
            selected_candidate_evidence=evidence,
            pre_review_predicted_value=candidate.value,
            decision=state,
            automatic_commit_permission=(
                AutomaticCommitPermission.PERMITTED
                if state is FieldDecisionState.AUTO_ACCEPTED
                else AutomaticCommitPermission.NOT_PERMITTED
            ),
            decision_reason="Synthetic frozen decision.",
            cached_unresolved_conflict=False,
            configuration_refs=configuration_refs,
        )

    def disposition(self, state: PolicyState) -> PreResolutionDisposition:
        return PreResolutionDisposition(
            state=state,
            gate_result=self.gate(),
            failure_stage=FailureStage.PRE_RESOLUTION
            if state is PolicyState.FAILED
            else None,
            failure_reason="Synthetic pre-resolution failure."
            if state is PolicyState.FAILED
            else None,
        )

    def test_records_are_frozen_and_slotted(self) -> None:
        record_types = (
            proposed_contracts.SourceCharacterSpanV1,
            proposed_contracts.B3CompatibleSeedV1,
            proposed_contracts.MethodReadyFieldV1,
            proposed_contracts.CandidateProvenanceV1,
            proposed_contracts.PreliminaryRankV1,
            proposed_contracts.CandidateRecordV1,
            proposed_contracts.ConstraintResultV1,
            proposed_contracts.ConfigurationRefV1,
            proposed_contracts.ConfigurationRefsV1,
            proposed_contracts.CandidateEvidenceV1,
            proposed_contracts.FieldDecisionV1,
            proposed_contracts.ReviewResolutionV1,
            proposed_contracts.FinalApplicationOutcomeV1,
            ProposedAdapterResultV1,
        )
        for record_type in record_types:
            with self.subTest(record_type=record_type.__name__):
                self.assertTrue(is_dataclass(record_type))
                self.assertTrue(record_type.__dataclass_params__.frozen)
                self.assertTrue(hasattr(record_type, "__slots__"))
        record = self.method_field()
        with self.assertRaises(FrozenInstanceError):
            record.c0_value = "changed"
        with self.assertRaises((AttributeError, TypeError)):
            record.extra = "not allowed"

    def test_method_ready_requires_exact_extracted_b2_identity_and_c0(self) -> None:
        record = self.method_field()
        with self.assertRaisesRegex(ValueError, "Permanent c0"):
            replace(record, c0_value="changed")
        with self.assertRaisesRegex(ValueError, "retain the B2 field ID"):
            replace(record, field_id="another-field")
        missing = StructuredField(
            field_id=self.FIELD_ID,
            receipt_id=self.RECEIPT_ID,
            field_name=ReceiptFieldName.STORE_NAME,
            status=FieldStatus.MISSING,
            unresolved_reason="Not found.",
        )
        with self.assertRaisesRegex(ValueError, "Only an EXTRACTED"):
            replace(record, original_b2_field=missing)

    def test_method_ready_requires_sufficient_stored_gate(self) -> None:
        record = self.method_field()
        self.assertEqual(
            SourceEvidenceDecision.SUFFICIENT,
            record.stored_gate_result.decision,
        )
        insufficient = SourceEvidenceGateResult(
            gate_result_id="contract-v1-insufficient-gate",
            receipt_id=self.RECEIPT_ID,
            decision=SourceEvidenceDecision.INSUFFICIENT,
            reasons=("Synthetic insufficient source evidence.",),
        )
        with self.assertRaisesRegex(ValueError, "stored SUFFICIENT"):
            replace(record, stored_gate_result=insufficient)

    def test_source_span_and_candidate_provenance_identity_are_validated(self) -> None:
        valid = SourceCharacterSpanV1("store-token", 0, 11, "PANTRY MART")
        self.assertEqual(11, valid.end - valid.start)
        with self.assertRaises(ValueError):
            SourceCharacterSpanV1("store-token", 3, 3, "x")
        with self.assertRaisesRegex(ValueError, "text length"):
            SourceCharacterSpanV1("store-token", 0, 999, "X")
        for start, end in ((False, 1), (0, True), (0.0, 1), (0, 1.0)):
            with self.subTest(start=start, end=end):
                with self.assertRaisesRegex(ValueError, "non-Boolean integers"):
                    SourceCharacterSpanV1("store-token", start, end, "X")
        with self.assertRaisesRegex(ValueError, "token_id"):
            SourceCharacterSpanV1("", 0, 1, "X")
        with self.assertRaisesRegex(ValueError, "record version"):
            SourceCharacterSpanV1("store-token", 0, 1, "X", record_version="2")
        provenance = self.altered_candidate().provenance[0]
        with self.assertRaisesRegex(ValueError, "declared source token"):
            replace(
                provenance,
                source_spans=(SourceCharacterSpanV1("other", 0, 1, "x"),),
            )
        with self.assertRaisesRegex(ValueError, "rule ID"):
            replace(provenance, generic_rule_id=None)

    def test_candidate_provenance_union_is_ordered_and_typed(self) -> None:
        candidate = self.altered_candidate()
        retailer = CandidateProvenanceV1(
            provenance_id="provenance-retailer",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            candidate_id=candidate.candidate_id,
            source_kind=CandidateSourceKind.RETAILER_MAPPING,
            original_observed_value="PANTRY MART",
            resource_snapshot_id="retailer-snapshot-v1",
        )
        merged = replace(candidate, provenance=(*candidate.provenance, retailer))
        self.assertEqual(
            (CandidateSourceKind.GENERIC_NORMALIZATION, CandidateSourceKind.RETAILER_MAPPING),
            tuple(item.source_kind for item in merged.provenance),
        )
        self.assertEqual((2, 3), tuple(item.source_priority for item in merged.provenance))

    def test_permanent_c0_cannot_be_limit_overflow(self) -> None:
        c0 = self.original_candidate()
        with self.assertRaisesRegex(ValueError, "cannot be removed"):
            replace(c0, limit_status=CandidateLimitStatus.LIMIT_OVERFLOW)
        overflow = self.altered_candidate(
            limit_status=CandidateLimitStatus.LIMIT_OVERFLOW
        )
        self.assertEqual(CandidateLimitStatus.LIMIT_OVERFLOW, overflow.limit_status)
        with self.assertRaisesRegex(ValueError, "cannot receive evidence audit"):
            CandidateEvidenceV1(
                evidence_id="overflow-evidence",
                candidate=overflow,
                constraint_result=self.constraint(overflow),
                candidate_status=CandidateAuditStatus.SCORING_ELIGIBLE,
                configuration_refs=self.configs(),
            )

    def test_constraint_identity_and_reason_codes_are_required(self) -> None:
        candidate = self.altered_candidate()
        constraint = self.constraint(candidate)
        with self.assertRaisesRegex(ValueError, "identity"):
            CandidateEvidenceV1(
                evidence_id="bad-identity",
                candidate=candidate,
                constraint_result=replace(constraint, field_id="wrong"),
                candidate_status=CandidateAuditStatus.SCORING_ELIGIBLE,
                configuration_refs=self.configs(),
            )
        with self.assertRaisesRegex(ValueError, "reason code"):
            ConstraintResultV1(
                constraint_result_id="rejected",
                receipt_id=self.RECEIPT_ID,
                field_id=self.FIELD_ID,
                candidate_id=candidate.candidate_id,
                eligibility=ConstraintEligibility.CONSTRAINT_REJECTED,
                evaluated_rule_ids=("TYPE-V1",),
                reason_detail="Rejected.",
            )

    def test_constraint_rejected_altered_candidate_has_na_evidence(self) -> None:
        candidate = self.altered_candidate()
        evidence = CandidateEvidenceV1(
            evidence_id="rejected-evidence",
            candidate=candidate,
            constraint_result=self.constraint(
                candidate, ConstraintEligibility.CONSTRAINT_REJECTED
            ),
            candidate_status=CandidateAuditStatus.CONSTRAINT_REJECTED,
            configuration_refs=self.configs(ready=False),
        )
        self.assertIsNone(evidence.raw_score)
        self.assertIsNone(evidence.calibrated_probability)
        self.assertFalse(evidence.probability_available)
        self.assertEqual(ValueAvailabilityStatus.NOT_APPLICABLE, evidence.score_status)
        with self.assertRaisesRegex(ValueError, "bypass"):
            replace(evidence, raw_score=Decimal("0.1"))

    def test_rejected_price_only_altered_candidate_never_scores(self) -> None:
        candidate = self.altered_candidate()
        evidence = CandidateEvidenceV1(
            evidence_id="price-only",
            candidate=candidate,
            constraint_result=self.constraint(candidate),
            candidate_status=CandidateAuditStatus.REJECTED_PRICE_ONLY,
            configuration_refs=self.configs(ready=False),
        )
        self.assertEqual((), evidence.feature_values)
        original = self.original_candidate()
        with self.assertRaisesRegex(ValueError, "altered"):
            replace(
                evidence,
                candidate=original,
                constraint_result=self.constraint(original),
            )

    def test_failed_c0_is_retained_but_cannot_be_auto_accepted(self) -> None:
        c0 = self.original_candidate()
        audit = CandidateEvidenceV1(
            evidence_id="failed-c0",
            candidate=c0,
            constraint_result=self.constraint(c0, ConstraintEligibility.CONSTRAINT_REJECTED),
            candidate_status=CandidateAuditStatus.CONSTRAINT_REJECTED,
            configuration_refs=self.configs(ready=False),
        )
        self.assertEqual(self.C0_ID, audit.candidate.candidate_id)
        self.assertEqual(CandidateLimitStatus.RETAINED, audit.candidate.limit_status)
        with self.assertRaisesRegex(ValueError, "eligible, probability-available"):
            replace(
                self.decision(FieldDecisionState.REVIEW_REQUIRED),
                selected_candidate=c0,
                selected_candidate_evidence=audit,
                pre_review_predicted_value=c0.value,
                decision=FieldDecisionState.AUTO_ACCEPTED,
                automatic_commit_permission=AutomaticCommitPermission.PERMITTED,
                configuration_refs=audit.configuration_refs,
            )

    def test_feature_order_mask_and_missing_values_are_exact(self) -> None:
        evidence = self.evidence()
        self.assertEqual(("q_o", "q_e", "a_l", "a_y", "s_r", "s_a", "s_p"), tuple(
            slot.value for slot in evidence.feature_slots
        ))
        with self.assertRaisesRegex(ValueError, "Equation 4.1 order"):
            replace(evidence, feature_slots=tuple(reversed(FEATURE_SLOT_ORDER)))
        with self.assertRaisesRegex(ValueError, "mask disagrees"):
            replace(
                evidence,
                missingness_mask=(False, False, False, False, True, False, True),
            )

    def test_raw_score_and_probability_are_distinct_decimal_values(self) -> None:
        evidence = self.evidence()
        self.assertEqual(Decimal("2.125"), evidence.raw_score)
        self.assertEqual(Decimal("0.8750"), evidence.calibrated_probability)
        self.assertNotEqual(evidence.raw_score, evidence.calibrated_probability)

    def test_available_calibration_requires_available_raw_score(self) -> None:
        evidence = self.evidence()
        with self.assertRaisesRegex(ValueError, "available raw score"):
            replace(
                evidence,
                score_status=ValueAvailabilityStatus.UNAVAILABLE,
                raw_score=None,
                score_reason="Synthetic scorer outage.",
            )

    def test_available_score_with_unavailable_calibration_is_valid(self) -> None:
        evidence = replace(
            self.evidence(),
            calibration_status=ValueAvailabilityStatus.UNAVAILABLE,
            probability_available=False,
            calibrated_probability=None,
            calibration_reason="Synthetic per-field calibration failure.",
        )
        self.assertEqual(ValueAvailabilityStatus.AVAILABLE, evidence.score_status)
        self.assertIsNotNone(evidence.raw_score)
        self.assertEqual(
            ConfigurationState.READY, evidence.configuration_refs.kappa.state
        )
        self.assertEqual(
            ValueAvailabilityStatus.UNAVAILABLE, evidence.calibration_status
        )
        self.assertIsNone(evidence.calibrated_probability)

    def test_not_ready_configuration_remains_distinct_from_runtime_failure(self) -> None:
        original = self.original_candidate()
        refs = replace(
            self.configs(),
            kappa=self.config_ref(
                ConfigurationKind.KAPPA, ConfigurationState.NOT_READY
            ),
        )
        evidence = replace(
            self.evidence(original),
            configuration_refs=refs,
            calibration_status=ValueAvailabilityStatus.UNAVAILABLE,
            probability_available=False,
            calibrated_probability=None,
            calibration_reason="Calibration configuration is NOT_READY.",
        )
        self.assertEqual(
            ConfigurationState.NOT_READY, evidence.configuration_refs.kappa.state
        )
        self.assertEqual(
            "Calibration configuration is NOT_READY.", evidence.calibration_reason
        )
        with self.assertRaisesRegex(ValueError, "probability-available"):
            self.decision(
                FieldDecisionState.AUTO_ACCEPTED,
                candidate=original,
                evidence=evidence,
                configuration_refs=refs,
            )

    def test_nonfinite_and_out_of_range_numbers_are_rejected(self) -> None:
        evidence = self.evidence()
        for invalid in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with self.subTest(raw_score=invalid):
                with self.assertRaises(ValueError):
                    replace(evidence, raw_score=invalid)
            with self.subTest(probability=invalid):
                with self.assertRaises(ValueError):
                    replace(evidence, calibrated_probability=invalid)
        with self.assertRaisesRegex(ValueError, r"within \[0, 1\]"):
            replace(evidence, calibrated_probability=Decimal("1.01"))
        with self.assertRaises(ValueError):
            PreliminaryRankV1(2, Decimal("NaN"), 0, "x", 1)

    def test_nullable_score_and_calibration_unavailability_are_explicit(self) -> None:
        candidate = self.altered_candidate()
        unavailable = replace(
            self.evidence(candidate),
            configuration_refs=self.configs(ready=False),
            score_status=ValueAvailabilityStatus.UNAVAILABLE,
            raw_score=None,
            score_reason="Scorer configuration is NOT_READY.",
            calibration_status=ValueAvailabilityStatus.UNAVAILABLE,
            probability_available=False,
            calibrated_probability=None,
            calibration_reason="Calibration configuration is NOT_READY.",
        )
        self.assertIsNone(unavailable.raw_score)
        self.assertIsNone(unavailable.calibrated_probability)

    def test_configuration_roles_and_unready_invalid_no_point_states(self) -> None:
        not_ready = self.configs(ready=False)
        self.assertEqual(ConfigurationState.NOT_READY, not_ready.theta_a.state)
        invalid_kappa = self.config_ref(ConfigurationKind.KAPPA, ConfigurationState.NOT_VALID)
        no_point = self.config_ref(ConfigurationKind.PT2, ConfigurationState.NO_VALID_POINT)
        refs = replace(not_ready, kappa=invalid_kappa, pt2=no_point)
        self.assertEqual(ConfigurationState.NOT_VALID, refs.kappa.state)
        self.assertEqual(ConfigurationState.NO_VALID_POINT, refs.pt2.state)
        with self.assertRaisesRegex(ValueError, "specific to PT2"):
            self.config_ref(ConfigurationKind.PT1, ConfigurationState.NO_VALID_POINT)
        with self.assertRaisesRegex(ValueError, "distinct roles"):
            replace(refs, theta_a=invalid_kappa)

    def test_field_decision_binds_to_method_ready_original_c0(self) -> None:
        decision = self.decision(FieldDecisionState.AUTO_ACCEPTED)
        for changes, message in (
            ({"receipt_id": "other-receipt"}, "belong to the receipt"),
            ({"field_id": "other-field"}, "identify the field"),
            ({"method_field_id": "other-method"}, "method-field identity"),
            ({"c0_candidate_id": "other-c0"}, "original c0 candidate ID"),
            ({"c0_value": "arbitrary"}, "original B2 value"),
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, message):
                    replace(decision, **changes)

    def test_original_and_altered_candidates_can_be_selected_with_bound_c0(self) -> None:
        original = self.original_candidate()
        original_evidence = self.evidence(original)
        original_decision = self.decision(
            FieldDecisionState.AUTO_ACCEPTED,
            candidate=original,
            evidence=original_evidence,
        )
        altered_decision = self.decision(FieldDecisionState.AUTO_ACCEPTED)

        self.assertEqual(CandidateRole.ORIGINAL, original_decision.selected_candidate.role)
        self.assertEqual("PANTRY MART", original_decision.pre_review_predicted_value)
        self.assertEqual(CandidateRole.ALTERED, altered_decision.selected_candidate.role)
        self.assertEqual("pantry mart", altered_decision.pre_review_predicted_value)
        self.assertEqual(
            original_decision.method_ready_field.c0_value,
            altered_decision.method_ready_field.c0_value,
        )

    def test_decision_and_evidence_configurations_must_match(self) -> None:
        decision = self.decision(FieldDecisionState.AUTO_ACCEPTED)
        for name in ("theta_a", "kappa", "phi"):
            reference = getattr(decision.configuration_refs, name)
            mismatched = replace(
                decision.configuration_refs,
                **{
                    name: replace(
                        reference,
                        configuration_id=f"different-{reference.configuration_id}",
                    )
                },
            )
            with self.subTest(configuration=name):
                with self.assertRaisesRegex(ValueError, "must match"):
                    replace(decision, configuration_refs=mismatched)

    def test_auto_accept_requires_ready_phi_but_not_ready_pt1_and_pt2(self) -> None:
        ready = self.configs()
        phi_not_ready = replace(
            ready,
            phi=self.config_ref(ConfigurationKind.PHI, ConfigurationState.NOT_READY),
        )
        phi_evidence = self.evidence(configuration_refs=phi_not_ready)
        with self.assertRaisesRegex(ValueError, "READY Phi"):
            self.decision(
                FieldDecisionState.AUTO_ACCEPTED,
                evidence=phi_evidence,
                configuration_refs=phi_not_ready,
            )

        evaluation_not_ready = replace(
            ready,
            pt1=self.config_ref(ConfigurationKind.PT1, ConfigurationState.NOT_READY),
            pt2=self.config_ref(
                ConfigurationKind.PT2, ConfigurationState.NO_VALID_POINT
            ),
        )
        evidence = self.evidence(configuration_refs=evaluation_not_ready)
        accepted = self.decision(
            FieldDecisionState.AUTO_ACCEPTED,
            evidence=evidence,
            configuration_refs=evaluation_not_ready,
        )
        self.assertEqual(ConfigurationState.NOT_READY, accepted.configuration_refs.pt1.state)
        self.assertEqual(
            ConfigurationState.NO_VALID_POINT, accepted.configuration_refs.pt2.state
        )

    def test_review_required_supports_unavailable_probability(self) -> None:
        original = self.original_candidate()
        evidence = replace(
            self.evidence(original),
            calibration_status=ValueAvailabilityStatus.UNAVAILABLE,
            probability_available=False,
            calibrated_probability=None,
            calibration_reason="Synthetic per-field calibration failure.",
        )
        decision = self.decision(
            FieldDecisionState.REVIEW_REQUIRED,
            candidate=original,
            evidence=evidence,
        )
        self.assertEqual(FieldDecisionState.REVIEW_REQUIRED, decision.decision)
        self.assertEqual(CandidateRole.ORIGINAL, decision.selected_candidate.role)
        self.assertEqual(decision.method_ready_field.c0_value, decision.c0_value)
        self.assertEqual(decision.c0_value, decision.pre_review_predicted_value)
        self.assertEqual(
            AutomaticCommitPermission.NOT_PERMITTED,
            decision.automatic_commit_permission,
        )
        self.assertEqual(
            ConfigurationState.READY, decision.configuration_refs.theta_a.state
        )
        self.assertEqual(
            ConfigurationState.READY, decision.configuration_refs.kappa.state
        )
        self.assertEqual(
            ConfigurationState.READY, decision.configuration_refs.phi.state
        )
        self.assertFalse(decision.selected_candidate_evidence.probability_available)
        self.assertEqual(
            ValueAvailabilityStatus.UNAVAILABLE,
            decision.selected_candidate_evidence.calibration_status,
        )
        self.assertEqual(
            "Synthetic per-field calibration failure.",
            decision.selected_candidate_evidence.calibration_reason,
        )

    def test_unavailable_probability_rejects_altered_frozen_prediction(self) -> None:
        altered = self.altered_candidate()
        evidence = replace(
            self.evidence(altered),
            calibration_status=ValueAvailabilityStatus.UNAVAILABLE,
            probability_available=False,
            calibrated_probability=None,
            calibration_reason="Synthetic per-field calibration failure.",
        )
        with self.assertRaisesRegex(ValueError, "permanent original c0 prediction"):
            self.decision(
                FieldDecisionState.REVIEW_REQUIRED,
                candidate=altered,
                evidence=evidence,
            )

    def test_field_auto_accepted_is_not_receipt_auto_resolved(self) -> None:
        decision = self.decision(FieldDecisionState.AUTO_ACCEPTED)
        self.assertEqual(FieldDecisionState.AUTO_ACCEPTED, decision.decision)
        self.assertNotIsInstance(decision.decision, PolicyState)
        outcome = FinalApplicationOutcomeV1(
            outcome_id="not-yet-persisted",
            receipt_id=self.RECEIPT_ID,
            pre_resolution=self.disposition(PolicyState.AUTO_RESOLVED),
            persistence_state=PersistenceResultState.NOT_ATTEMPTED,
            field_decisions=(decision,),
        )
        self.assertEqual(PolicyState.AUTO_RESOLVED, outcome.pre_resolution.state)

    def test_field_decision_rejects_mismatched_candidate_audit(self) -> None:
        decision = self.decision()
        other = self.original_candidate()
        with self.assertRaisesRegex(ValueError, "immutable candidate record"):
            replace(
                decision,
                selected_candidate_evidence=self.evidence(other),
            )

    def test_oracle_and_user_review_resolutions_are_separate(self) -> None:
        decision = self.decision()
        oracle = ReviewResolutionV1(
            resolution_id="oracle-resolution",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_decision=decision,
            resolution_kind=ReviewResolutionKind.ORACLE_POLICY_RESOLVED,
            presented_value=decision.pre_review_predicted_value,
            actor_reference="tier-a-reference",
            resolution_event_id="oracle-event-1",
            resolved_value="PANTRY MART",
        )
        confirmed = ReviewResolutionV1(
            resolution_id="user-confirmation",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_decision=decision,
            resolution_kind=ReviewResolutionKind.USER_CONFIRMED,
            presented_value=decision.pre_review_predicted_value,
            actor_reference="local-user-action",
            resolution_event_id="user-event-1",
            resolved_value=decision.pre_review_predicted_value,
        )
        self.assertFalse(oracle.production_persistence_eligible)
        self.assertTrue(confirmed.production_persistence_eligible)
        with self.assertRaisesRegex(ValueError, "actual changed"):
            replace(
                confirmed,
                resolution_kind=ReviewResolutionKind.USER_MODIFIED,
            )

    def test_review_resolution_requires_actor_and_realized_event_references(self) -> None:
        decision = self.decision()
        confirmed = ReviewResolutionV1(
            resolution_id="user-confirmation",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_decision=decision,
            resolution_kind=ReviewResolutionKind.USER_CONFIRMED,
            presented_value=decision.pre_review_predicted_value,
            actor_reference="local-user-action",
            resolution_event_id="user-event-1",
            resolved_value=decision.pre_review_predicted_value,
        )
        for changes, message in (
            ({"actor_reference": ""}, "actor_reference"),
            ({"resolution_event_id": ""}, "resolution_event_id"),
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, message):
                    replace(confirmed, **changes)

    def test_oracle_or_unresolved_review_cannot_commit(self) -> None:
        decision = self.decision()
        oracle = ReviewResolutionV1(
            resolution_id="oracle-resolution",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_decision=decision,
            resolution_kind=ReviewResolutionKind.ORACLE_POLICY_RESOLVED,
            presented_value=decision.pre_review_predicted_value,
            actor_reference="tier-a-reference",
            resolution_event_id="oracle-event-1",
            resolved_value="PANTRY MART",
        )
        base = dict(
            outcome_id="review-outcome",
            receipt_id=self.RECEIPT_ID,
            pre_resolution=self.disposition(PolicyState.REVIEW_REQUIRED),
            persistence_state=PersistenceResultState.COMMITTED,
            field_decisions=(decision,),
            persistence_attempt_id="attempt-1",
            inventory_write_reference="write-1",
            successful_persistence_evidence_id="sqlite-transaction-success-1",
        )
        with self.assertRaisesRegex(ValueError, "not persistence-eligible"):
            FinalApplicationOutcomeV1(**base)
        with self.assertRaisesRegex(ValueError, "not persistence-eligible"):
            FinalApplicationOutcomeV1(**base, review_resolutions=(oracle,))

    def test_user_resolution_can_authorize_but_does_not_claim_commit(self) -> None:
        decision = self.decision()
        confirmed = ReviewResolutionV1(
            resolution_id="user-confirmation",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_decision=decision,
            resolution_kind=ReviewResolutionKind.USER_CONFIRMED,
            presented_value=decision.pre_review_predicted_value,
            actor_reference="local-user-action",
            resolution_event_id="user-event-1",
            resolved_value=decision.pre_review_predicted_value,
        )
        authorized = FinalApplicationOutcomeV1(
            outcome_id="authorized-not-attempted",
            receipt_id=self.RECEIPT_ID,
            pre_resolution=self.disposition(PolicyState.REVIEW_REQUIRED),
            persistence_state=PersistenceResultState.NOT_ATTEMPTED,
            field_decisions=(decision,),
            review_resolutions=(confirmed,),
        )
        self.assertEqual(PersistenceResultState.NOT_ATTEMPTED, authorized.persistence_state)

    def test_single_user_confirmation_or_modification_can_authorize_commit(self) -> None:
        decision = self.decision()
        resolutions = (
            ReviewResolutionV1(
                resolution_id="user-confirmation",
                receipt_id=self.RECEIPT_ID,
                field_id=self.FIELD_ID,
                field_decision=decision,
                resolution_kind=ReviewResolutionKind.USER_CONFIRMED,
                presented_value=decision.pre_review_predicted_value,
                actor_reference="local-user-action",
                resolution_event_id="user-event-confirm",
                resolved_value=decision.pre_review_predicted_value,
            ),
            ReviewResolutionV1(
                resolution_id="user-modification",
                receipt_id=self.RECEIPT_ID,
                field_id=self.FIELD_ID,
                field_decision=decision,
                resolution_kind=ReviewResolutionKind.USER_MODIFIED,
                presented_value=decision.pre_review_predicted_value,
                actor_reference="local-user-action",
                resolution_event_id="user-event-modify",
                resolved_value="PANTRY MART USER VALUE",
            ),
        )
        for index, resolution in enumerate(resolutions):
            with self.subTest(kind=resolution.resolution_kind):
                outcome = FinalApplicationOutcomeV1(
                    outcome_id=f"user-commit-{index}",
                    receipt_id=self.RECEIPT_ID,
                    pre_resolution=self.disposition(PolicyState.REVIEW_REQUIRED),
                    persistence_state=PersistenceResultState.COMMITTED,
                    field_decisions=(decision,),
                    review_resolutions=(resolution,),
                    persistence_attempt_id=f"attempt-{index}",
                    inventory_write_reference=f"write-{index}",
                    successful_persistence_evidence_id=f"success-{index}",
                )
                self.assertEqual(PersistenceResultState.COMMITTED, outcome.persistence_state)

    def test_duplicate_field_decisions_cannot_authorize_commit(self) -> None:
        first = self.decision(FieldDecisionState.AUTO_ACCEPTED)
        duplicate_field = replace(first, decision_id=f"{self.FIELD_ID}:decision:2")
        with self.assertRaisesRegex(ValueError, "field decision field IDs"):
            FinalApplicationOutcomeV1(
                outcome_id="duplicate-field-decisions",
                receipt_id=self.RECEIPT_ID,
                pre_resolution=self.disposition(PolicyState.AUTO_RESOLVED),
                persistence_state=PersistenceResultState.COMMITTED,
                field_decisions=(first, duplicate_field),
                persistence_attempt_id="attempt-duplicate-fields",
                inventory_write_reference="write-duplicate-fields",
                successful_persistence_evidence_id="success-duplicate-fields",
            )

    def test_duplicate_resolutions_for_one_decision_cannot_authorize_commit(self) -> None:
        decision = self.decision()
        first = ReviewResolutionV1(
            resolution_id="user-confirmation-1",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_decision=decision,
            resolution_kind=ReviewResolutionKind.USER_CONFIRMED,
            presented_value=decision.pre_review_predicted_value,
            actor_reference="local-user-action",
            resolution_event_id="user-event-1",
            resolved_value=decision.pre_review_predicted_value,
        )
        second = replace(
            first,
            resolution_id="user-confirmation-2",
            resolution_event_id="user-event-2",
        )
        with self.assertRaisesRegex(ValueError, "review-resolution decision IDs"):
            FinalApplicationOutcomeV1(
                outcome_id="duplicate-resolutions",
                receipt_id=self.RECEIPT_ID,
                pre_resolution=self.disposition(PolicyState.REVIEW_REQUIRED),
                persistence_state=PersistenceResultState.COMMITTED,
                field_decisions=(decision,),
                review_resolutions=(first, second),
                persistence_attempt_id="attempt-duplicate-resolutions",
                inventory_write_reference="write-duplicate-resolutions",
                successful_persistence_evidence_id="success-duplicate-resolutions",
            )

    def test_resolution_must_match_complete_supplied_decision_record(self) -> None:
        supplied = self.decision()
        contradictory = replace(
            supplied,
            decision_reason="Different immutable decision content.",
        )
        resolution = ReviewResolutionV1(
            resolution_id="contradictory-confirmation",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_decision=contradictory,
            resolution_kind=ReviewResolutionKind.USER_CONFIRMED,
            presented_value=contradictory.pre_review_predicted_value,
            actor_reference="local-user-action",
            resolution_event_id="user-event-contradictory",
            resolved_value=contradictory.pre_review_predicted_value,
        )
        with self.assertRaisesRegex(ValueError, "immutable supplied field decision"):
            FinalApplicationOutcomeV1(
                outcome_id="contradictory-resolution",
                receipt_id=self.RECEIPT_ID,
                pre_resolution=self.disposition(PolicyState.REVIEW_REQUIRED),
                persistence_state=PersistenceResultState.COMMITTED,
                field_decisions=(supplied,),
                review_resolutions=(resolution,),
                persistence_attempt_id="attempt-contradictory",
                inventory_write_reference="write-contradictory",
                successful_persistence_evidence_id="success-contradictory",
            )

    def test_unbound_resolution_cannot_authorize_commit(self) -> None:
        supplied = self.decision()
        unrelated = replace(
            supplied,
            decision_id=f"{self.FIELD_ID}:unbound-decision",
        )
        resolution = ReviewResolutionV1(
            resolution_id="unbound-confirmation",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            field_decision=unrelated,
            resolution_kind=ReviewResolutionKind.USER_CONFIRMED,
            presented_value=unrelated.pre_review_predicted_value,
            actor_reference="local-user-action",
            resolution_event_id="user-event-unbound",
            resolved_value=unrelated.pre_review_predicted_value,
        )
        with self.assertRaisesRegex(ValueError, "bind to a supplied field decision"):
            FinalApplicationOutcomeV1(
                outcome_id="unbound-resolution",
                receipt_id=self.RECEIPT_ID,
                pre_resolution=self.disposition(PolicyState.REVIEW_REQUIRED),
                persistence_state=PersistenceResultState.COMMITTED,
                field_decisions=(supplied,),
                review_resolutions=(resolution,),
                persistence_attempt_id="attempt-unbound",
                inventory_write_reference="write-unbound",
                successful_persistence_evidence_id="success-unbound",
            )

    def test_committed_and_failed_results_preserve_frozen_disposition(self) -> None:
        decision = self.decision(FieldDecisionState.AUTO_ACCEPTED)
        disposition = self.disposition(PolicyState.AUTO_RESOLVED)
        committed = FinalApplicationOutcomeV1(
            outcome_id="committed",
            receipt_id=self.RECEIPT_ID,
            pre_resolution=disposition,
            persistence_state=PersistenceResultState.COMMITTED,
            field_decisions=(decision,),
            persistence_attempt_id="attempt-1",
            inventory_write_reference="write-1",
            successful_persistence_evidence_id="sqlite-transaction-success-1",
        )
        failed = FinalApplicationOutcomeV1(
            outcome_id="failed-write",
            receipt_id=self.RECEIPT_ID,
            pre_resolution=disposition,
            persistence_state=PersistenceResultState.FAILED,
            field_decisions=(decision,),
            persistence_attempt_id="attempt-2",
            failure_stage=FailureStage.INVENTORY_PERSISTENCE,
            failure_reason="Synthetic write exception.",
        )
        self.assertIs(disposition, committed.pre_resolution)
        self.assertIs(disposition, failed.pre_resolution)
        self.assertEqual(PolicyState.AUTO_RESOLVED, failed.pre_resolution.state)

    def test_fallback_and_pre_resolution_failure_never_enter_persistence(self) -> None:
        decision = self.decision(FieldDecisionState.AUTO_ACCEPTED)
        insufficient_gate = SourceEvidenceGateResult(
            gate_result_id="insufficient",
            receipt_id=self.RECEIPT_ID,
            decision=SourceEvidenceDecision.INSUFFICIENT,
            reasons=("Synthetic insufficiency.",),
        )
        fallback = PreResolutionDisposition(
            state=PolicyState.FALLBACK_NO_UPDATE,
            gate_result=insufficient_gate,
        )
        for disposition in (fallback, self.disposition(PolicyState.FAILED)):
            with self.subTest(state=disposition.state):
                with self.assertRaisesRegex(ValueError, "not persistence-eligible"):
                    FinalApplicationOutcomeV1(
                        outcome_id=f"bad-{disposition.state.value}",
                        receipt_id=self.RECEIPT_ID,
                        pre_resolution=disposition,
                        persistence_state=PersistenceResultState.COMMITTED,
                        field_decisions=(decision,),
                        persistence_attempt_id="attempt",
                        inventory_write_reference="write",
                        successful_persistence_evidence_id="success-evidence",
                    )

    def test_committed_shape_requires_attempt_and_write_references(self) -> None:
        with self.assertRaises(ValueError):
            FinalApplicationOutcomeV1(
                outcome_id="intent-only",
                receipt_id=self.RECEIPT_ID,
                pre_resolution=self.disposition(PolicyState.AUTO_RESOLVED),
                persistence_state=PersistenceResultState.COMMITTED,
                field_decisions=(self.decision(FieldDecisionState.AUTO_ACCEPTED),),
            )

    def test_deterministic_json_preserves_enums_nulls_and_decimals(self) -> None:
        evidence = self.evidence()
        first = to_deterministic_json(evidence)
        second = to_deterministic_json(evidence)
        self.assertEqual(first, second)
        self.assertIn('"candidate_status":"SCORING_ELIGIBLE"', first)
        self.assertIn('"calibrated_probability":"0.8750"', first)
        self.assertIn('null', first)


if __name__ == "__main__":
    unittest.main()
