"""Synthetic tests for structural trusted-Theta_A records."""

from __future__ import annotations

from dataclasses import replace
import unittest

from pipeline.proposed.contracts import (
    FEATURE_SCHEMA_ID_V1,
    FEATURE_SLOT_ORDER,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
)
from pipeline.proposed.trusted_theta_contracts_v1 import (
    RESTRICTED_CANONICAL_JSON_PROFILE,
    DecimalRoundingPolicyV1,
    DigestAlgorithmV1,
    TrustedResolverReasonV1,
    TrustedResolverResultError,
    TrustedResolverStateV1,
    TrustedScorerBindingError,
    TrustedScorerBindingV1,
    TrustedScorerResolverResultV1,
    TrustedThetaManifestError,
    TrustedThetaManifestV1,
)


def _theta() -> ConfigurationRefV1:
    return ConfigurationRefV1(
        kind=ConfigurationKind.THETA_A,
        configuration_id="theta-a-synthetic",
        configuration_version="v0",
        state=ConfigurationState.READY,
        content_hash="synthetic-structural-hash",
    )


def _manifest(**changes: object) -> TrustedThetaManifestV1:
    values: dict[str, object] = {
        "manifest_id": "manifest-synthetic",
        "manifest_version": "v1",
        "parent_theta_a": _theta(),
        "feature_schema_id": FEATURE_SCHEMA_ID_V1,
        "feature_schema_version": "1",
        "feature_slot_order": FEATURE_SLOT_ORDER,
        "missing_policy_id": "missing-policy",
        "missing_policy_version": "v1",
        "not_applicable_policy_id": "na-policy",
        "not_applicable_policy_version": "v1",
        "admission_policy_id": "admission-policy",
        "admission_policy_version": "v1",
        "scorer_component_id": "synthetic-scorer",
        "scorer_component_version": "v0",
        "artifact_id": "artifact-synthetic",
        "artifact_version": "v0",
        "artifact_format": "SYNTHETIC_TEST_ONLY",
        "artifact_byte_length": 128,
        "artifact_digest_algorithm": DigestAlgorithmV1.SHA256,
        "artifact_digest": "a" * 64,
        "canonical_encoding_id": RESTRICTED_CANONICAL_JSON_PROFILE,
        "canonical_encoding_version": "1",
        "manifest_digest_algorithm": DigestAlgorithmV1.SHA256,
        "manifest_digest": "b" * 64,
        "trust_registry_id": "registry-synthetic",
        "trust_registry_version": "v1",
        "trust_entry_id": "entry-synthetic",
        "approval_authority_id": "authority-synthetic",
        "approval_record_id": "approval-synthetic",
        "runtime_identifier": "cpython",
        "runtime_version": "synthetic",
        "abi_identifier": "synthetic-abi",
        "dependency_lock_digest_algorithm": DigestAlgorithmV1.SHA256,
        "dependency_lock_digest": "c" * 64,
        "deterministic_policy_id": "determinism-policy",
        "deterministic_policy_version": "v1",
        "numeric_precision": 16,
        "numeric_scale": 4,
        "rounding_policy": DecimalRoundingPolicyV1.ROUND_HALF_EVEN,
        "compatibility_policy_id": "compatibility-policy",
        "compatibility_policy_version": "v1",
        "offline_snapshot_id": "snapshot-synthetic",
        "offline_snapshot_version": "v1",
    }
    values.update(changes)
    return TrustedThetaManifestV1(**values)  # type: ignore[arg-type]


def _ready_result(**changes: object) -> TrustedScorerResolverResultV1:
    manifest = _manifest()
    binding = TrustedScorerBindingV1.from_manifest(
        binding_id="binding-synthetic",
        manifest=manifest,
    )
    values: dict[str, object] = {
        "resolver_result_id": "resolver-result-synthetic",
        "resolver_component_id": "resolver-interface",
        "resolver_component_version": "v1",
        "state": TrustedResolverStateV1.READY,
        "reason": None,
        "retryable": False,
        "parent_theta_a": manifest.parent_theta_a,
        "registry_snapshot_id": "snapshot-synthetic",
        "registry_snapshot_version": "v1",
        "registry_snapshot_digest_algorithm": DigestAlgorithmV1.SHA256,
        "registry_snapshot_digest": "d" * 64,
        "manifest": manifest,
        "binding": binding,
        "runtime_fingerprint": "synthetic-runtime-fingerprint",
        "evidence_references": ("synthetic-structural-evidence",),
    }
    values.update(changes)
    return TrustedScorerResolverResultV1(**values)  # type: ignore[arg-type]


class TrustedThetaManifestTests(unittest.TestCase):
    def test_valid_manifest_preserves_all_structural_metadata(self) -> None:
        manifest = _manifest()
        self.assertEqual(manifest.feature_slot_order, FEATURE_SLOT_ORDER)
        self.assertEqual(manifest.numeric_scale, 4)
        self.assertIs(manifest.parent_theta_a.kind, ConfigurationKind.THETA_A)

    def test_manifest_rejects_wrong_theta_kind_and_state(self) -> None:
        for theta in (
            replace(_theta(), kind=ConfigurationKind.KAPPA),
            ConfigurationRefV1(
                kind=ConfigurationKind.THETA_A,
                configuration_id="theta-a-synthetic",
                configuration_version="v0",
                state=ConfigurationState.NOT_READY,
                status_reason="missing",
            ),
        ):
            with self.subTest(theta=theta):
                with self.assertRaises(TrustedThetaManifestError):
                    _manifest(parent_theta_a=theta)

    def test_manifest_rejects_schema_and_slot_order_drift(self) -> None:
        with self.assertRaises(TrustedThetaManifestError):
            _manifest(feature_schema_id="different")
        with self.assertRaises(TrustedThetaManifestError):
            _manifest(feature_slot_order=tuple(reversed(FEATURE_SLOT_ORDER)))

    def test_manifest_rejects_malformed_digests(self) -> None:
        for field in (
            "artifact_digest",
            "manifest_digest",
            "dependency_lock_digest",
        ):
            with self.subTest(field=field):
                with self.assertRaises(TrustedThetaManifestError):
                    _manifest(**{field: "ABC"})

    def test_manifest_rejects_boolean_or_invalid_numeric_policy(self) -> None:
        for changes in (
            {"artifact_byte_length": True},
            {"numeric_precision": 0},
            {"numeric_scale": -1},
            {"rounding_policy": "ROUND_HALF_EVEN"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(TrustedThetaManifestError):
                    _manifest(**changes)

    def test_manifest_rejects_self_supersession(self) -> None:
        with self.assertRaises(TrustedThetaManifestError):
            _manifest(supersedes_manifest_id="manifest-synthetic")

    def test_structural_digest_is_not_computed_or_authenticated(self) -> None:
        first = _manifest(manifest_digest="1" * 64)
        second = _manifest(manifest_digest="2" * 64)
        self.assertNotEqual(first.manifest_digest, second.manifest_digest)


class TrustedScorerBindingTests(unittest.TestCase):
    def test_binding_factory_copies_exact_manifest_relationships(self) -> None:
        manifest = _manifest()
        binding = TrustedScorerBindingV1.from_manifest(
            binding_id="binding-synthetic",
            manifest=manifest,
        )
        self.assertEqual(binding.parent_theta_a, manifest.parent_theta_a)
        self.assertEqual(binding.manifest_digest, manifest.manifest_digest)
        self.assertEqual(binding.artifact_digest, manifest.artifact_digest)
        self.assertEqual(binding.numeric_scale, manifest.numeric_scale)

    def test_binding_factory_rejects_structurally_revoked_manifest(self) -> None:
        with self.assertRaises(TrustedScorerBindingError):
            TrustedScorerBindingV1.from_manifest(
                binding_id="binding-synthetic",
                manifest=_manifest(revocation_reference="revocation-1"),
            )

    def test_binding_rejects_feature_order_and_nonfinite_structure_drift(self) -> None:
        binding = TrustedScorerBindingV1.from_manifest(
            binding_id="binding-synthetic",
            manifest=_manifest(),
        )
        with self.assertRaises(TrustedScorerBindingError):
            replace(binding, feature_slot_order=tuple(reversed(FEATURE_SLOT_ORDER)))
        with self.assertRaises(TrustedScorerBindingError):
            replace(binding, artifact_byte_length=False)


class TrustedResolverResultTests(unittest.TestCase):
    def test_synthetic_ready_result_is_structurally_valid_only(self) -> None:
        result = _ready_result()
        self.assertIs(result.state, TrustedResolverStateV1.READY)
        self.assertIsNotNone(result.manifest)
        self.assertIsNotNone(result.binding)

    def test_ready_requires_manifest_binding_snapshot_and_evidence(self) -> None:
        for changes in (
            {"manifest": None},
            {"binding": None},
            {"registry_snapshot_id": None},
            {"runtime_fingerprint": None},
            {"evidence_references": ()},
            {"reason": TrustedResolverReasonV1.ARTIFACT_NOT_AVAILABLE},
            {"retryable": True},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(TrustedResolverResultError):
                    _ready_result(**changes)

    def test_ready_snapshot_must_match_manifest_offline_snapshot(self) -> None:
        for changes in (
            {"registry_snapshot_id": "different-snapshot"},
            {"registry_snapshot_version": "different-version"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(TrustedResolverResultError):
                    _ready_result(**changes)

    def test_ready_rejects_binding_that_differs_from_manifest(self) -> None:
        result = _ready_result()
        assert result.binding is not None
        with self.assertRaises(TrustedResolverResultError):
            _ready_result(binding=replace(result.binding, artifact_digest="e" * 64))

    def test_value_equal_distinct_theta_is_accepted(self) -> None:
        result = _ready_result(parent_theta_a=replace(_theta()))
        self.assertEqual(result.parent_theta_a, result.manifest.parent_theta_a)  # type: ignore[union-attr]

    def test_theta_content_mismatch_is_rejected(self) -> None:
        with self.assertRaises(TrustedResolverResultError):
            _ready_result(
                parent_theta_a=replace(
                    _theta(), configuration_version="different-version"
                )
            )

    def test_not_ready_requires_missing_prerequisite_and_no_binding(self) -> None:
        manifest = _manifest()
        result = TrustedScorerResolverResultV1(
            resolver_result_id="not-ready",
            resolver_component_id="resolver-interface",
            resolver_component_version="v1",
            state=TrustedResolverStateV1.NOT_READY,
            reason=TrustedResolverReasonV1.ARTIFACT_NOT_AVAILABLE,
            retryable=True,
            parent_theta_a=manifest.parent_theta_a,
            registry_snapshot_id=manifest.offline_snapshot_id,
            registry_snapshot_version=manifest.offline_snapshot_version,
            registry_snapshot_digest_algorithm=DigestAlgorithmV1.SHA256,
            registry_snapshot_digest="d" * 64,
            manifest=manifest,
            binding=None,
            runtime_fingerprint=None,
            evidence_references=(),
        )
        self.assertIs(result.state, TrustedResolverStateV1.NOT_READY)
        with self.assertRaises(TrustedResolverResultError):
            replace(result, reason=TrustedResolverReasonV1.ARTIFACT_DIGEST_MISMATCH)

    def test_not_ready_reason_must_match_available_structural_evidence(self) -> None:
        manifest = _manifest()
        common: dict[str, object] = {
            "resolver_result_id": "resolver-not-ready",
            "resolver_component_id": "resolver-interface",
            "resolver_component_version": "v1",
            "state": TrustedResolverStateV1.NOT_READY,
            "retryable": True,
            "parent_theta_a": manifest.parent_theta_a,
            "registry_snapshot_digest_algorithm": DigestAlgorithmV1.SHA256,
            "registry_snapshot_digest": "d" * 64,
            "binding": None,
            "runtime_fingerprint": None,
            "evidence_references": (),
        }
        invalid = (
            {
                "reason": TrustedResolverReasonV1.TRUST_SNAPSHOT_NOT_AVAILABLE,
                "registry_snapshot_id": manifest.offline_snapshot_id,
                "registry_snapshot_version": manifest.offline_snapshot_version,
                "manifest": None,
            },
            {
                "reason": TrustedResolverReasonV1.MANIFEST_NOT_AVAILABLE,
                "registry_snapshot_id": manifest.offline_snapshot_id,
                "registry_snapshot_version": manifest.offline_snapshot_version,
                "manifest": manifest,
            },
            {
                "reason": TrustedResolverReasonV1.ARTIFACT_NOT_AVAILABLE,
                "registry_snapshot_id": None,
                "registry_snapshot_version": None,
                "registry_snapshot_digest_algorithm": None,
                "registry_snapshot_digest": None,
                "manifest": manifest,
            },
            {
                "reason": TrustedResolverReasonV1.RUNTIME_DEPENDENCY_NOT_AVAILABLE,
                "registry_snapshot_id": manifest.offline_snapshot_id,
                "registry_snapshot_version": manifest.offline_snapshot_version,
                "manifest": None,
            },
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises(TrustedResolverResultError):
                    TrustedScorerResolverResultV1(
                        **(common | changes)  # type: ignore[arg-type]
                    )

    def test_not_valid_requires_contradiction_evidence_and_no_binding(self) -> None:
        result = TrustedScorerResolverResultV1(
            resolver_result_id="not-valid",
            resolver_component_id="resolver-interface",
            resolver_component_version="v1",
            state=TrustedResolverStateV1.NOT_VALID,
            reason=TrustedResolverReasonV1.ARTIFACT_DIGEST_MISMATCH,
            retryable=False,
            parent_theta_a=_theta(),
            registry_snapshot_id="snapshot",
            registry_snapshot_version="v1",
            registry_snapshot_digest_algorithm=DigestAlgorithmV1.SHA256,
            registry_snapshot_digest="d" * 64,
            manifest=_manifest(),
            binding=None,
            runtime_fingerprint="synthetic-runtime",
            evidence_references=("digest-comparison",),
        )
        self.assertIs(result.state, TrustedResolverStateV1.NOT_VALID)
        with self.assertRaises(TrustedResolverResultError):
            replace(result, evidence_references=())

    def test_legacy_configuration_ready_is_not_resolver_ready(self) -> None:
        theta = _theta()
        self.assertIs(theta.state, ConfigurationState.READY)
        self.assertNotIsInstance(theta, TrustedScorerResolverResultV1)

    def test_nested_theta_mutation_is_revalidated(self) -> None:
        result = _ready_result()
        object.__setattr__(result.parent_theta_a, "kind", ConfigurationKind.KAPPA)
        with self.assertRaises(TrustedResolverResultError):
            result.__post_init__()


if __name__ == "__main__":
    unittest.main()
