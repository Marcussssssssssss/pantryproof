"""Synthetic structural tests for V2-native raw-scoring evidence."""

from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

import pipeline.proposed.backend_observational_path as backend_path
from pipeline.proposed.contracts import FEATURE_SCHEMA_ID_V1, FEATURE_SLOT_ORDER
from pipeline.proposed.feature_construction import construct_purchase_date_features_v0
from pipeline.proposed.scoring_contracts_v2 import (
    AdmissionStateV2,
    CandidateScoreEvidenceV2,
    FieldScoringAuditV2,
    FieldScoringCompletionStateV2,
    FieldScoringFailureStateV2,
    FieldScoringFailureV2,
    PreScoreAdmissionEvidenceV2,
    ScoreNotApplicableReasonV2,
    ScoreStatusV2,
    ScorerInvocationStateV2,
    ScoringAuditIntegrityError,
    ScoringOperationResultV2,
    ScoringSourceBindingError,
    construct_scoring_source_snapshot_v2,
)
from pipeline.proposed.trusted_theta_contracts_v1 import (
    RESTRICTED_CANONICAL_JSON_PROFILE,
    DecimalRoundingPolicyV1,
    DigestAlgorithmV1,
    TrustedResolverReasonV1,
    TrustedResolverStateV1,
    TrustedScorerBindingV1,
    TrustedScorerResolverResultV1,
    TrustedThetaManifestV1,
)
import test_proposed_backend_observational_path as backend_fixtures


_ADMISSION_POLICY_ID = "synthetic-admission-policy"
_ADMISSION_POLICY_VERSION = "v1"
_COMPONENT_ID = "synthetic-structural-scoring"
_COMPONENT_VERSION = "v0"


def _manifest(theta, **changes: object) -> TrustedThetaManifestV1:
    values: dict[str, object] = {
        "manifest_id": "synthetic-scoring-manifest",
        "manifest_version": "v1",
        "parent_theta_a": theta,
        "feature_schema_id": FEATURE_SCHEMA_ID_V1,
        "feature_schema_version": "1",
        "feature_slot_order": FEATURE_SLOT_ORDER,
        "missing_policy_id": "synthetic-missing-policy",
        "missing_policy_version": "v1",
        "not_applicable_policy_id": "synthetic-na-policy",
        "not_applicable_policy_version": "v1",
        "admission_policy_id": _ADMISSION_POLICY_ID,
        "admission_policy_version": _ADMISSION_POLICY_VERSION,
        "scorer_component_id": "synthetic-scorer-not-operational",
        "scorer_component_version": "v0",
        "artifact_id": "synthetic-artifact-not-real",
        "artifact_version": "v0",
        "artifact_format": "SYNTHETIC_CONFORMANCE_ONLY",
        "artifact_byte_length": 128,
        "artifact_digest_algorithm": DigestAlgorithmV1.SHA256,
        "artifact_digest": "a" * 64,
        "canonical_encoding_id": RESTRICTED_CANONICAL_JSON_PROFILE,
        "canonical_encoding_version": "1",
        "manifest_digest_algorithm": DigestAlgorithmV1.SHA256,
        "manifest_digest": "b" * 64,
        "trust_registry_id": "synthetic-registry-not-operational",
        "trust_registry_version": "v1",
        "trust_entry_id": "synthetic-entry",
        "approval_authority_id": "synthetic-test-authority",
        "approval_record_id": "synthetic-test-record",
        "runtime_identifier": "cpython",
        "runtime_version": "synthetic",
        "abi_identifier": "synthetic-abi",
        "dependency_lock_digest_algorithm": DigestAlgorithmV1.SHA256,
        "dependency_lock_digest": "c" * 64,
        "deterministic_policy_id": "synthetic-determinism",
        "deterministic_policy_version": "v1",
        "numeric_precision": 16,
        "numeric_scale": 4,
        "rounding_policy": DecimalRoundingPolicyV1.ROUND_HALF_EVEN,
        "compatibility_policy_id": "synthetic-compatibility",
        "compatibility_policy_version": "v1",
        "offline_snapshot_id": "synthetic-offline-snapshot",
        "offline_snapshot_version": "v1",
    }
    values.update(changes)
    return TrustedThetaManifestV1(**values)  # type: ignore[arg-type]


def _resolver(theta, state: TrustedResolverStateV1):
    manifest = _manifest(theta)
    if state is TrustedResolverStateV1.READY:
        binding = TrustedScorerBindingV1.from_manifest(
            binding_id="synthetic-binding",
            manifest=manifest,
        )
        return TrustedScorerResolverResultV1(
            resolver_result_id="synthetic-resolver-ready",
            resolver_component_id="synthetic-resolver-interface",
            resolver_component_version="v1",
            state=state,
            reason=None,
            retryable=False,
            parent_theta_a=theta,
            registry_snapshot_id=manifest.offline_snapshot_id,
            registry_snapshot_version=manifest.offline_snapshot_version,
            registry_snapshot_digest_algorithm=DigestAlgorithmV1.SHA256,
            registry_snapshot_digest="d" * 64,
            manifest=manifest,
            binding=binding,
            runtime_fingerprint="synthetic-runtime",
            evidence_references=("synthetic-structural-check",),
        )
    if state is TrustedResolverStateV1.NOT_READY:
        reason = TrustedResolverReasonV1.ARTIFACT_NOT_AVAILABLE
        retryable = True
        evidence = ()
    else:
        reason = TrustedResolverReasonV1.ARTIFACT_DIGEST_MISMATCH
        retryable = False
        evidence = ("synthetic-contradiction",)
    has_missing_artifact = state is TrustedResolverStateV1.NOT_READY
    return TrustedScorerResolverResultV1(
        resolver_result_id=f"synthetic-resolver-{state.value.lower()}",
        resolver_component_id="synthetic-resolver-interface",
        resolver_component_version="v1",
        state=state,
        reason=reason,
        retryable=retryable,
        parent_theta_a=theta,
        registry_snapshot_id=(
            manifest.offline_snapshot_id if has_missing_artifact else None
        ),
        registry_snapshot_version=(
            manifest.offline_snapshot_version if has_missing_artifact else None
        ),
        registry_snapshot_digest_algorithm=(
            DigestAlgorithmV1.SHA256 if has_missing_artifact else None
        ),
        registry_snapshot_digest=("d" * 64 if has_missing_artifact else None),
        manifest=(manifest if has_missing_artifact else None),
        binding=None,
        runtime_fingerprint=None,
        evidence_references=evidence,
    )


def _admission(candidate, result, feature, state: AdmissionStateV2, index: int):
    evaluated = state in (
        AdmissionStateV2.ADMITTED,
        AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT,
    )
    return PreScoreAdmissionEvidenceV2(
        admission_id=f"synthetic-admission-{index}",
        source_snapshot_id="synthetic-source-snapshot",
        candidate=candidate,
        constraint_result=result,
        feature_vector=feature,
        state=state,
        policy_id=_ADMISSION_POLICY_ID if evaluated else None,
        policy_version=_ADMISSION_POLICY_VERSION if evaluated else None,
        evidence_references=(f"synthetic-evidence-{index}",) if evaluated else (),
        component_id=_COMPONENT_ID,
        component_version=_COMPONENT_VERSION,
    )


def _score(admission, index: int, binding=None):
    if admission.state is AdmissionStateV2.ADMITTED:
        return CandidateScoreEvidenceV2(
            score_evidence_id=f"synthetic-score-{index}",
            admission=admission,
            score_status=ScoreStatusV2.AVAILABLE,
            raw_score=Decimal("0.8750"),
            not_applicable_reason=None,
            trusted_scorer_binding=binding,
            component_id=_COMPONENT_ID,
            component_version=_COMPONENT_VERSION,
        )
    reasons = {
        AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_REJECTED:
            ScoreNotApplicableReasonV2.CONSTRAINT_REJECTED,
        AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE:
            ScoreNotApplicableReasonV2.CONSTRAINT_UNAVAILABLE,
        AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT:
            ScoreNotApplicableReasonV2.PRE_SCORE_REJECTED_PRICE_ONLY_SUPPORT,
    }
    return CandidateScoreEvidenceV2(
        score_evidence_id=f"synthetic-score-{index}",
        admission=admission,
        score_status=ScoreStatusV2.NOT_APPLICABLE,
        raw_score=None,
        not_applicable_reason=reasons[admission.state],
        trusted_scorer_binding=None,
        component_id=_COMPONENT_ID,
        component_version=_COMPONENT_VERSION,
    )


def build_structural_records() -> dict[str, object]:
    """Create one fully synthetic graph shared by contract and codec tests."""

    backend = backend_fixtures.ProposedBackendObservationalPathTests(
        methodName="runTest"
    )
    backend.setUp()
    inputs = backend.inputs(
        synthetic_values=("31/02/2026", "10/11/2026"),
        candidate_limit=3,
    )
    operand, constraints = backend_path._execute_purchase_date_observational_graph_v0(
        **inputs
    )
    feature_result = construct_purchase_date_features_v0(
        operand_audit=operand,
        constraint_results=constraints,
    )
    snapshot = construct_scoring_source_snapshot_v2(
        source_snapshot_id="synthetic-source-snapshot",
        feature_construction_result=feature_result,
    )
    resolver = _resolver(snapshot.theta_a_reference, TrustedResolverStateV1.READY)
    binding = resolver.binding
    assert binding is not None
    features = {
        feature.candidate.candidate_id: feature
        for feature in snapshot.candidate_features
    }
    states_by_aggregate = {
        "ELIGIBLE": AdmissionStateV2.ADMITTED,
        "CONSTRAINT_REJECTED": (
            AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_REJECTED
        ),
        "CONSTRAINT_UNAVAILABLE": (
            AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE
        ),
    }
    admissions = tuple(
        _admission(
            candidate,
            result,
            features.get(candidate.candidate_id),
            states_by_aggregate[result.aggregate_state.value],
            index,
        )
        for index, (candidate, result) in enumerate(
            zip(snapshot.candidates, snapshot.constraint_results, strict=True)
        )
    )
    scores = tuple(
        _score(admission, index, binding)
        for index, admission in enumerate(admissions)
    )
    audit = FieldScoringAuditV2(
        field_audit_id="synthetic-field-audit",
        source_snapshot=snapshot,
        candidate_scores=scores,
        admitted_candidate_ids=(snapshot.candidates[0].candidate_id,),
        admitted_candidate_count=1,
        resolver_invocation=ScorerInvocationStateV2.INVOKED,
        resolver_result=resolver,
        trusted_scorer_binding=binding,
        completion_state=FieldScoringCompletionStateV2.COMPLETE_SCORED,
        component_id=_COMPONENT_ID,
        component_version=_COMPONENT_VERSION,
    )
    return {
        "inputs": inputs,
        "snapshot": snapshot,
        "manifest": resolver.manifest,
        "binding": binding,
        "resolver": resolver,
        "admissions": admissions,
        "scores": scores,
        "audit": audit,
        "operation": ScoringOperationResultV2(
            operation_result_id="synthetic-operation",
            outcome=audit,
        ),
    }


def build_zero_admitted_audit(records=None):
    records = build_structural_records() if records is None else records
    snapshot = records["snapshot"]
    original_admissions = records["admissions"]
    first = _admission(
        snapshot.candidates[0],
        snapshot.constraint_results[0],
        snapshot.candidate_features[0],
        AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT,
        0,
    )
    admissions = (first, *original_admissions[1:])
    scores = tuple(_score(admission, index) for index, admission in enumerate(admissions))
    return FieldScoringAuditV2(
        field_audit_id="synthetic-zero-bypass",
        source_snapshot=snapshot,
        candidate_scores=scores,
        admitted_candidate_ids=(),
        admitted_candidate_count=0,
        resolver_invocation=ScorerInvocationStateV2.NOT_INVOKED_ZERO_ADMITTED,
        resolver_result=None,
        trusted_scorer_binding=None,
        completion_state=FieldScoringCompletionStateV2.COMPLETE_ZERO_ADMITTED_BYPASS,
        component_id=_COMPONENT_ID,
        component_version=_COMPONENT_VERSION,
    )


class ProposedScoringContractsV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = build_structural_records()

    def fresh(self):
        return build_structural_records()

    def test_complete_population_preserves_c0_order_and_exact_sources(self) -> None:
        records = self.records
        snapshot = records["snapshot"]
        audit = records["audit"]
        self.assertIs(snapshot.c0_candidate, snapshot.candidates[0])
        self.assertEqual(3, len(snapshot.candidates))
        self.assertEqual(3, len(audit.candidate_scores))
        for entry, candidate, result in zip(
            audit.candidate_scores,
            snapshot.candidates,
            snapshot.constraint_results,
            strict=True,
        ):
            self.assertIs(entry.candidate, candidate)
            self.assertIs(entry.constraint_result, result)
            self.assertIs(result.c0_candidate, snapshot.c0_candidate)

    def test_v2_rejected_and_unavailable_remain_distinct_not_applicable(self) -> None:
        by_reason = {
            score.not_applicable_reason: score
            for score in self.records["scores"]
            if score.score_status is ScoreStatusV2.NOT_APPLICABLE
        }
        rejected = by_reason[ScoreNotApplicableReasonV2.CONSTRAINT_REJECTED]
        unavailable = by_reason[ScoreNotApplicableReasonV2.CONSTRAINT_UNAVAILABLE]
        self.assertIs(
            rejected.not_applicable_reason,
            ScoreNotApplicableReasonV2.CONSTRAINT_REJECTED,
        )
        self.assertIs(
            unavailable.not_applicable_reason,
            ScoreNotApplicableReasonV2.CONSTRAINT_UNAVAILABLE,
        )
        self.assertIsNone(rejected.raw_score)
        self.assertIsNone(unavailable.raw_score)

    def test_price_only_rejection_preserves_original_v2_eligible_state(self) -> None:
        bypass = build_zero_admitted_audit(self.fresh())
        first = bypass.candidate_scores[0]
        self.assertEqual("ELIGIBLE", first.constraint_result.aggregate_state.value)
        self.assertIs(
            first.admission.state,
            AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT,
        )

    def test_admission_rejects_v2_state_contradictions(self) -> None:
        records = self.fresh()
        rejected = next(
            result
            for result in records["snapshot"].constraint_results
            if result.aggregate_state.value == "CONSTRAINT_REJECTED"
        )
        with self.assertRaises(ScoringAuditIntegrityError):
            _admission(
                rejected.candidate,
                rejected,
                None,
                AdmissionStateV2.ADMITTED,
                99,
            )

    def test_admission_rejects_arbitrary_policy_boolean_substitute(self) -> None:
        records = self.fresh()
        admitted = records["admissions"][0]
        with self.assertRaises(ScoringAuditIntegrityError):
            replace(admitted, policy_id=None, policy_version=None)

    def test_available_score_requires_finite_decimal_and_binding(self) -> None:
        records = self.fresh()
        available = records["scores"][0]
        for value in (None, Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=value), self.assertRaises(ScoringAuditIntegrityError):
                replace(available, raw_score=value)
        with self.assertRaises(ScoringAuditIntegrityError):
            replace(available, trusted_scorer_binding=None)

    def test_numeric_policy_rejects_scale_precision_and_negative_zero(self) -> None:
        available = self.fresh()["scores"][0]
        for value in (
            Decimal("0.875"),
            Decimal("0.87500"),
            Decimal("-0.0000"),
            Decimal("1234567890123.4567"),
        ):
            with self.subTest(value=value), self.assertRaises(ScoringAuditIntegrityError):
                replace(available, raw_score=value)

    def test_candidate_local_unavailable_state_does_not_exist(self) -> None:
        self.assertEqual(("AVAILABLE", "NOT_APPLICABLE"), tuple(item.value for item in ScoreStatusV2))

    def test_not_applicable_score_requires_null_and_exact_reason(self) -> None:
        rejected = next(
            score
            for score in self.fresh()["scores"]
            if score.not_applicable_reason
            is ScoreNotApplicableReasonV2.CONSTRAINT_REJECTED
        )
        with self.assertRaises(ScoringAuditIntegrityError):
            replace(rejected, raw_score=Decimal("0.0000"))
        with self.assertRaises(ScoringAuditIntegrityError):
            replace(
                rejected,
                not_applicable_reason=ScoreNotApplicableReasonV2.CONSTRAINT_UNAVAILABLE,
            )

    def test_zero_admitted_bypass_has_no_resolver_or_binding(self) -> None:
        audit = build_zero_admitted_audit(self.fresh())
        self.assertEqual(0, audit.admitted_candidate_count)
        self.assertIsNone(audit.resolver_result)
        self.assertIsNone(audit.trusted_scorer_binding)
        self.assertIs(
            audit.resolver_invocation,
            ScorerInvocationStateV2.NOT_INVOKED_ZERO_ADMITTED,
        )
        self.assertTrue(
            all(score.score_status is ScoreStatusV2.NOT_APPLICABLE for score in audit.candidate_scores)
        )

    def test_zero_bypass_rejects_fabricated_ready_and_wrong_invocation(self) -> None:
        records = self.fresh()
        audit = build_zero_admitted_audit(records)
        with self.assertRaises(ScoringAuditIntegrityError):
            replace(
                audit,
                resolver_invocation=ScorerInvocationStateV2.INVOKED,
                resolver_result=records["resolver"],
                trusted_scorer_binding=records["binding"],
            )

    def test_missing_extra_duplicate_and_reordered_scores_are_rejected(self) -> None:
        records = self.fresh()
        audit = records["audit"]
        candidates = audit.candidate_scores
        for changed in (
            candidates[:-1],
            (*candidates, candidates[-1]),
            (candidates[0], candidates[1], candidates[1]),
            tuple(reversed(candidates)),
        ):
            with self.subTest(length=len(changed)), self.assertRaises(
                (ScoringAuditIntegrityError, ScoringSourceBindingError)
            ):
                replace(audit, candidate_scores=changed)

    def test_value_equal_constraint_and_feature_substitution_is_rejected(self) -> None:
        records = self.fresh()
        admission = records["admissions"][0]
        copied_result = replace(admission.constraint_result)
        copied_feature = replace(
            admission.feature_vector,
            constraint_result=copied_result,
        )
        copied_admission = replace(
            admission,
            constraint_result=copied_result,
            feature_vector=copied_feature,
        )
        copied_score = replace(records["scores"][0], admission=copied_admission)
        with self.assertRaises(ScoringSourceBindingError):
            replace(
                records["audit"],
                candidate_scores=(copied_score, *records["scores"][1:]),
            )

    def test_success_and_failure_reject_cross_snapshot_admission(self) -> None:
        records = self.fresh()
        admission = replace(
            records["admissions"][0],
            source_snapshot_id="different-source-snapshot",
        )
        score = replace(records["scores"][0], admission=admission)
        with self.assertRaises(ScoringSourceBindingError):
            replace(
                records["audit"],
                candidate_scores=(score, *records["scores"][1:]),
            )

        resolver = _resolver(
            records["snapshot"].theta_a_reference,
            TrustedResolverStateV1.NOT_READY,
        )
        with self.assertRaises(ScoringSourceBindingError):
            FieldScoringFailureV2(
                failure_id="synthetic-cross-snapshot-failure",
                source_snapshot=records["snapshot"],
                admissions=(admission, *records["admissions"][1:]),
                admitted_candidate_ids=(records["snapshot"].candidates[0].candidate_id,),
                resolver_invocation=ScorerInvocationStateV2.INVOKED,
                resolver_result=resolver,
                failure_state=FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_READY,
                failure_code="NOT_READY",
                component_id=_COMPONENT_ID,
                component_version=_COMPONENT_VERSION,
            )

    def test_post_construction_source_substitution_is_rejected(self) -> None:
        records = self.fresh()
        snapshot = records["snapshot"]
        object.__setattr__(
            snapshot,
            "feature_construction_result",
            replace(snapshot.feature_construction_result),
        )
        with self.assertRaises(ScoringSourceBindingError):
            snapshot.__post_init__()

    def test_partial_score_aggregate_is_rejected_atomically(self) -> None:
        records = self.fresh()
        audit = records["audit"]
        with self.assertRaises(ScoringAuditIntegrityError):
            replace(audit, candidate_scores=audit.candidate_scores[:1])

    def test_resolver_and_admission_manifest_bindings_are_exact(self) -> None:
        records = self.fresh()
        audit = records["audit"]
        wrong_policy = replace(
            audit.candidate_scores[0].admission,
            policy_id="different-policy",
        )
        wrong_score = replace(audit.candidate_scores[0], admission=wrong_policy)
        with self.assertRaises(ScoringAuditIntegrityError):
            replace(
                audit,
                candidate_scores=(wrong_score, *audit.candidate_scores[1:]),
            )

    def test_not_ready_and_not_valid_are_field_failures(self) -> None:
        records = self.fresh()
        admissions = records["admissions"]
        for resolver_state, failure_state in (
            (
                TrustedResolverStateV1.NOT_READY,
                FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_READY,
            ),
            (
                TrustedResolverStateV1.NOT_VALID,
                FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_VALID,
            ),
        ):
            with self.subTest(state=resolver_state):
                resolver = _resolver(
                    records["snapshot"].theta_a_reference,
                    resolver_state,
                )
                failure = FieldScoringFailureV2(
                    failure_id=f"synthetic-failure-{resolver_state.value}",
                    source_snapshot=records["snapshot"],
                    admissions=admissions,
                    admitted_candidate_ids=(records["snapshot"].candidates[0].candidate_id,),
                    resolver_invocation=ScorerInvocationStateV2.INVOKED,
                    resolver_result=resolver,
                    failure_state=failure_state,
                    failure_code=resolver_state.value,
                    component_id=_COMPONENT_ID,
                    component_version=_COMPONENT_VERSION,
                )
                self.assertIs(failure.resolver_result, resolver)
                self.assertFalse(hasattr(failure, "candidate_scores"))

    def test_failure_rejects_zero_admitted_and_state_mismatch(self) -> None:
        records = self.fresh()
        bypass = build_zero_admitted_audit(records)
        admissions = tuple(score.admission for score in bypass.candidate_scores)
        resolver = _resolver(
            records["snapshot"].theta_a_reference,
            TrustedResolverStateV1.NOT_READY,
        )
        values = dict(
            failure_id="synthetic-failure",
            source_snapshot=records["snapshot"],
            admissions=admissions,
            admitted_candidate_ids=(),
            resolver_invocation=ScorerInvocationStateV2.INVOKED,
            resolver_result=resolver,
            failure_state=FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_READY,
            failure_code="NOT_READY",
            component_id=_COMPONENT_ID,
            component_version=_COMPONENT_VERSION,
        )
        with self.assertRaises(ScoringAuditIntegrityError):
            FieldScoringFailureV2(**values)
        with self.assertRaises(ScoringAuditIntegrityError):
            FieldScoringFailureV2(
                **{
                    **values,
                    "admissions": records["admissions"],
                    "admitted_candidate_ids": (records["snapshot"].candidates[0].candidate_id,),
                    "failure_state": FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_VALID,
                }
            )

        with self.assertRaises(ScoringAuditIntegrityError):
            FieldScoringFailureV2(
                **{
                    **values,
                    "admissions": records["admissions"],
                    "admitted_candidate_ids": (records["snapshot"].candidates[0].candidate_id,),
                    "failure_state": FieldScoringFailureStateV2.CONFIGURATION_FAILURE,
                }
            )

    def test_failure_rejects_value_equal_feature_substitution(self) -> None:
        records = self.fresh()
        first = records["admissions"][0]
        copied_feature = replace(first.feature_vector)
        copied_admission = replace(first, feature_vector=copied_feature)
        resolver = _resolver(
            records["snapshot"].theta_a_reference,
            TrustedResolverStateV1.NOT_READY,
        )
        with self.assertRaises(ScoringSourceBindingError):
            FieldScoringFailureV2(
                failure_id="synthetic-substitution-failure",
                source_snapshot=records["snapshot"],
                admissions=(copied_admission, *records["admissions"][1:]),
                admitted_candidate_ids=(records["snapshot"].candidates[0].candidate_id,),
                resolver_invocation=ScorerInvocationStateV2.INVOKED,
                resolver_result=resolver,
                failure_state=FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_READY,
                failure_code="NOT_READY",
                component_id=_COMPONENT_ID,
                component_version=_COMPONENT_VERSION,
            )

    def test_operation_result_preserves_exact_outcome_reference(self) -> None:
        operation = self.fresh()["operation"]
        self.assertIs(operation.outcome, operation.outcome)
        object.__setattr__(operation, "outcome", replace(operation.outcome))
        with self.assertRaises(ScoringSourceBindingError):
            operation.__post_init__()

    def test_repeated_structural_construction_is_deterministic_by_value(self) -> None:
        first = self.fresh()["audit"]
        second = self.fresh()["audit"]
        self.assertEqual(first, second)
        self.assertIsNot(first, second)


if __name__ == "__main__":
    unittest.main()
