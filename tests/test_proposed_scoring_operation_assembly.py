"""Synthetic tests for the zero-admitted scoring-operation assembler."""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

import pipeline.proposed.backend_observational_path as backend_path
from pipeline.proposed.feature_construction import construct_purchase_date_features_v0
from pipeline.proposed.scoring_codec_v2 import (
    expected_admission_id,
    expected_field_audit_id,
    expected_operation_result_id,
    expected_score_evidence_id,
    expected_source_snapshot_id,
    scoring_operation_result_v2_from_json_bytes,
    scoring_operation_result_v2_to_json_bytes,
)
from pipeline.proposed.scoring_contracts_v2 import (
    AdmissionStateV2,
    FieldScoringAuditV2,
    FieldScoringCompletionStateV2,
    PreScoreAdmissionEvidenceV2,
    ScoreNotApplicableReasonV2,
    ScoreStatusV2,
    ScorerInvocationStateV2,
    ScoringAuditIntegrityError,
    ScoringOperationResultV2,
    ScoringSourceBindingError,
    construct_scoring_source_snapshot_v2,
)
from pipeline.proposed.scoring_operation_assembly import (
    SCORING_OPERATION_ASSEMBLY_COMPONENT_ID,
    SCORING_OPERATION_ASSEMBLY_COMPONENT_VERSION,
    ScoringOperationDeferredError,
    assemble_zero_admitted_scoring_operation_v0,
)
from pipeline.proposed.trusted_theta_contracts_v1 import (
    TrustedScorerResolverResultV1,
)

try:
    import test_proposed_backend_observational_path as backend_fixtures
except ModuleNotFoundError:  # Focused ``python -m unittest tests...`` invocation.
    from tests import test_proposed_backend_observational_path as backend_fixtures


_ADMISSION_COMPONENT_ID = "synthetic-admission-observation"
_ADMISSION_COMPONENT_VERSION = "v0"
_ADMISSION_POLICY_ID = "synthetic-price-support-policy"
_ADMISSION_POLICY_VERSION = "v0"


def _source_graph(
    synthetic_values: tuple[str, ...] = ("31/02/2026", "10/11/2026"),
):
    backend = backend_fixtures.ProposedBackendObservationalPathTests(
        methodName="runTest"
    )
    backend.setUp()
    inputs = backend.inputs(
        synthetic_values=synthetic_values,
        candidate_limit=1 + len(synthetic_values),
    )
    operand_audit, constraint_results = (
        backend_path._execute_purchase_date_observational_graph_v0(**inputs)
    )
    feature_result = construct_purchase_date_features_v0(
        operand_audit=operand_audit,
        constraint_results=constraint_results,
    )
    snapshot = construct_scoring_source_snapshot_v2(
        source_snapshot_id="pending-deterministic-id",
        feature_construction_result=feature_result,
    )
    return replace(
        snapshot,
        source_snapshot_id=expected_source_snapshot_id(snapshot),
    )


def _admission(
    *,
    snapshot,
    index: int,
    state: AdmissionStateV2,
) -> PreScoreAdmissionEvidenceV2:
    candidate = snapshot.candidates[index]
    constraint_result = snapshot.constraint_results[index]
    features = {
        feature.candidate.candidate_id: feature
        for feature in snapshot.candidate_features
    }
    evaluated = state in (
        AdmissionStateV2.ADMITTED,
        AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT,
    )
    admission = PreScoreAdmissionEvidenceV2(
        admission_id="pending-deterministic-id",
        source_snapshot_id=snapshot.source_snapshot_id,
        candidate=candidate,
        constraint_result=constraint_result,
        feature_vector=features.get(candidate.candidate_id),
        state=state,
        policy_id=_ADMISSION_POLICY_ID if evaluated else None,
        policy_version=_ADMISSION_POLICY_VERSION if evaluated else None,
        evidence_references=(f"synthetic-admission-evidence-{index}",)
        if evaluated
        else (),
        component_id=_ADMISSION_COMPONENT_ID,
        component_version=_ADMISSION_COMPONENT_VERSION,
    )
    return replace(
        admission,
        admission_id=expected_admission_id(admission),
    )


def _state_for_result(result, *, admit_eligible: bool) -> AdmissionStateV2:
    if result.aggregate_state.value == "ELIGIBLE":
        return (
            AdmissionStateV2.ADMITTED
            if admit_eligible
            else AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT
        )
    if result.aggregate_state.value == "CONSTRAINT_REJECTED":
        return AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_REJECTED
    return AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE


def _inputs(
    synthetic_values: tuple[str, ...] = ("31/02/2026", "10/11/2026"),
    *,
    admit_eligible: bool = False,
):
    snapshot = _source_graph(synthetic_values)
    admissions = tuple(
        _admission(
            snapshot=snapshot,
            index=index,
            state=_state_for_result(result, admit_eligible=admit_eligible),
        )
        for index, result in enumerate(snapshot.constraint_results)
    )
    return snapshot, admissions


def _assemble(snapshot, admissions) -> ScoringOperationResultV2:
    return assemble_zero_admitted_scoring_operation_v0(
        source_snapshot=snapshot,
        admissions=admissions,
    )


class ProposedScoringOperationAssemblyTests(unittest.TestCase):
    def test_valid_zero_admitted_population_preserves_c0_and_order(self) -> None:
        snapshot, admissions = _inputs()

        operation = _assemble(snapshot, admissions)

        self.assertIsInstance(operation, ScoringOperationResultV2)
        self.assertIsInstance(operation.outcome, FieldScoringAuditV2)
        audit = operation.outcome
        self.assertIs(audit.source_snapshot, snapshot)
        self.assertIs(audit.source_snapshot.c0_candidate, snapshot.candidates[0])
        self.assertEqual(
            tuple(candidate.candidate_id for candidate in snapshot.candidates),
            tuple(score.candidate.candidate_id for score in audit.candidate_scores),
        )
        self.assertEqual((), audit.admitted_candidate_ids)
        self.assertEqual(0, audit.admitted_candidate_count)
        self.assertIs(
            FieldScoringCompletionStateV2.COMPLETE_ZERO_ADMITTED_BYPASS,
            audit.completion_state,
        )
        self.assertIs(
            ScorerInvocationStateV2.NOT_INVOKED_ZERO_ADMITTED,
            audit.resolver_invocation,
        )
        self.assertIsNone(audit.resolver_result)
        self.assertIsNone(audit.trusted_scorer_binding)

    def test_mixed_states_map_to_exact_not_applicable_reasons(self) -> None:
        snapshot, admissions = _inputs()
        operation = _assemble(snapshot, admissions)
        expected = {
            AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT: (
                ScoreNotApplicableReasonV2.PRE_SCORE_REJECTED_PRICE_ONLY_SUPPORT
            ),
            AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_REJECTED: (
                ScoreNotApplicableReasonV2.CONSTRAINT_REJECTED
            ),
            AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE: (
                ScoreNotApplicableReasonV2.CONSTRAINT_UNAVAILABLE
            ),
        }
        self.assertEqual(3, len(set(item.state for item in admissions)))
        for score, admission in zip(
            operation.outcome.candidate_scores, admissions, strict=True
        ):
            self.assertIs(score.admission, admission)
            self.assertIs(ScoreStatusV2.NOT_APPLICABLE, score.score_status)
            self.assertIsNone(score.raw_score)
            self.assertIs(expected[admission.state], score.not_applicable_reason)
            self.assertIsNone(score.trusted_scorer_binding)

    def test_exact_v2_feature_and_theta_sources_are_preserved(self) -> None:
        snapshot, admissions = _inputs()
        audit = _assemble(snapshot, admissions).outcome
        features = {
            item.candidate.candidate_id: item for item in snapshot.candidate_features
        }
        for index, score in enumerate(audit.candidate_scores):
            self.assertIs(score.constraint_result, snapshot.constraint_results[index])
            self.assertIs(
                score.feature_vector,
                features.get(score.candidate.candidate_id),
            )
            self.assertEqual(
                snapshot.theta_a_reference,
                score.constraint_result.theta_a_reference,
            )

    def test_deterministic_ids_serialization_and_source_bound_round_trip(self) -> None:
        snapshot, admissions = _inputs()
        first = _assemble(snapshot, admissions)
        second = _assemble(snapshot, admissions)

        self.assertEqual(first, second)
        self.assertEqual(
            expected_field_audit_id(first.outcome), first.outcome.field_audit_id
        )
        self.assertEqual(
            expected_operation_result_id(first), first.operation_result_id
        )
        for score in first.outcome.candidate_scores:
            self.assertEqual(
                expected_score_evidence_id(score), score.score_evidence_id
            )
        first_bytes = scoring_operation_result_v2_to_json_bytes(first)
        self.assertEqual(
            first_bytes,
            scoring_operation_result_v2_to_json_bytes(second),
        )
        decoded = scoring_operation_result_v2_from_json_bytes(
            first_bytes,
            source_snapshot=snapshot,
        )
        self.assertEqual(first, decoded)
        self.assertIs(decoded.outcome.source_snapshot, snapshot)

    def test_missing_and_extra_admissions_reject(self) -> None:
        snapshot, admissions = _inputs()
        with self.assertRaisesRegex(ScoringAuditIntegrityError, "Exactly one"):
            _assemble(snapshot, admissions[:-1])
        with self.assertRaisesRegex(ScoringAuditIntegrityError, "Exactly one"):
            _assemble(snapshot, (*admissions, admissions[-1]))

    def test_duplicate_and_reordered_admissions_reject(self) -> None:
        snapshot, admissions = _inputs()
        duplicate = (admissions[0], admissions[0], *admissions[2:])
        with self.assertRaises(ScoringAuditIntegrityError):
            _assemble(snapshot, duplicate)
        reordered = (admissions[1], admissions[0], *admissions[2:])
        with self.assertRaises(ScoringSourceBindingError):
            _assemble(snapshot, reordered)

    def test_cross_snapshot_admission_rejects(self) -> None:
        snapshot, admissions = _inputs()
        cross = replace(admissions[0], source_snapshot_id="different-snapshot")
        cross = replace(cross, admission_id=expected_admission_id(cross))
        with self.assertRaisesRegex(ScoringSourceBindingError, "different"):
            _assemble(snapshot, (cross, *admissions[1:]))

    def test_substituted_candidate_identity_rejects(self) -> None:
        snapshot, admissions = _inputs()
        object.__setattr__(
            admissions[0], "candidate", replace(admissions[0].candidate)
        )
        with self.assertRaises(ScoringSourceBindingError):
            _assemble(snapshot, admissions)

    def test_substituted_v2_or_feature_identity_rejects(self) -> None:
        for attribute in ("constraint_result", "feature_vector"):
            with self.subTest(attribute=attribute):
                snapshot, admissions = _inputs()
                current = getattr(admissions[0], attribute)
                self.assertIsNotNone(current)
                object.__setattr__(admissions[0], attribute, replace(current))
                with self.assertRaises(ScoringSourceBindingError):
                    _assemble(snapshot, admissions)

    def test_tampered_deterministic_ids_reject(self) -> None:
        snapshot, admissions = _inputs()
        with self.assertRaisesRegex(
            ScoringAuditIntegrityError, "SourceSnapshot.*ID"
        ):
            _assemble(
                replace(snapshot, source_snapshot_id="tampered-snapshot-id"),
                admissions,
            )
        bad_admission = replace(admissions[0], admission_id="tampered-admission-id")
        with self.assertRaisesRegex(ScoringAuditIntegrityError, "Admission.*ID"):
            _assemble(snapshot, (bad_admission, *admissions[1:]))

    def test_incorrect_record_and_component_versions_reject(self) -> None:
        snapshot, admissions = _inputs()
        object.__setattr__(snapshot, "record_version", "unsupported")
        with self.assertRaisesRegex(ScoringAuditIntegrityError, "record version"):
            _assemble(snapshot, admissions)

        snapshot, admissions = _inputs()
        object.__setattr__(admissions[0], "record_version", "unsupported")
        with self.assertRaisesRegex(ScoringAuditIntegrityError, "admission record"):
            _assemble(snapshot, admissions)

        snapshot, admissions = _inputs()
        object.__setattr__(snapshot, "component_version", "unsupported")
        with self.assertRaisesRegex(ScoringAuditIntegrityError, "component version"):
            _assemble(snapshot, admissions)

    def test_malformed_source_snapshot_fails_before_assembly(self) -> None:
        snapshot, admissions = _inputs()
        object.__setattr__(snapshot, "source_component_versions", ("wrong",))
        with self.assertRaises(ScoringAuditIntegrityError):
            _assemble(snapshot, admissions)

    def test_one_valid_admitted_candidate_is_deferred(self) -> None:
        snapshot, admissions = _inputs(admit_eligible=True)
        self.assertEqual(
            1,
            sum(item.state is AdmissionStateV2.ADMITTED for item in admissions),
        )
        with self.assertRaises(ScoringOperationDeferredError):
            _assemble(snapshot, admissions)

    def test_multiple_valid_admitted_candidates_are_deferred(self) -> None:
        snapshot, admissions = _inputs(
            ("2026-10-25", "11/11/2026"),
            admit_eligible=True,
        )
        self.assertGreaterEqual(
            sum(item.state is AdmissionStateV2.ADMITTED for item in admissions),
            2,
        )
        with self.assertRaises(ScoringOperationDeferredError):
            _assemble(snapshot, admissions)

    def test_validation_failure_precedes_deferred_operation(self) -> None:
        snapshot, admissions = _inputs(admit_eligible=True)
        invalid = replace(admissions[0], admission_id="tampered-admitted-id")
        with self.assertRaises(ScoringAuditIntegrityError):
            _assemble(snapshot, (invalid, *admissions[1:]))

    def test_bypass_does_not_invoke_resolver_or_create_empirical_evidence(self) -> None:
        snapshot, admissions = _inputs()
        with patch.object(
            TrustedScorerResolverResultV1,
            "__post_init__",
            side_effect=AssertionError("resolver must not run"),
        ):
            operation = _assemble(snapshot, admissions)
        audit = operation.outcome
        self.assertIsNone(audit.resolver_result)
        self.assertIsNone(audit.trusted_scorer_binding)
        self.assertFalse(hasattr(operation, "probability"))
        self.assertFalse(hasattr(operation, "selected_candidate"))
        self.assertTrue(all(score.raw_score is None for score in audit.candidate_scores))

    def test_component_identity_is_fixed_and_inputs_are_not_mutated(self) -> None:
        snapshot, admissions = _inputs()
        original_admissions = admissions
        operation = _assemble(snapshot, admissions)
        audit = operation.outcome
        self.assertEqual(
            SCORING_OPERATION_ASSEMBLY_COMPONENT_ID,
            audit.component_id,
        )
        self.assertEqual(
            SCORING_OPERATION_ASSEMBLY_COMPONENT_VERSION,
            audit.component_version,
        )
        self.assertEqual(original_admissions, admissions)
        for score, admission in zip(audit.candidate_scores, admissions, strict=True):
            self.assertIs(score.admission, admission)
            self.assertEqual(
                SCORING_OPERATION_ASSEMBLY_COMPONENT_ID,
                score.component_id,
            )
            self.assertEqual(
                SCORING_OPERATION_ASSEMBLY_COMPONENT_VERSION,
                score.component_version,
            )


if __name__ == "__main__":
    unittest.main()
