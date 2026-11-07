"""Structural trusted-Theta_A manifest and resolver records.

These records do not authenticate a manifest, resolve or load an artifact,
execute a scorer, or establish empirical scorer validity.  A structurally
valid ``READY`` record is synthetic contract evidence until separately
approved trust infrastructure exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from pipeline.proposed.contracts import (
    FEATURE_SCHEMA_ID_V1,
    FEATURE_SLOT_ORDER,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    FeatureSlot,
)


TRUSTED_THETA_RECORD_VERSION = "trusted-theta-record-v1"
TRUSTED_THETA_MANIFEST_SCHEMA_ID = "pantryproof-trusted-theta-manifest-v1"
TRUSTED_THETA_MANIFEST_SCHEMA_VERSION = "1"
RESTRICTED_CANONICAL_JSON_PROFILE = "pantryproof-restricted-jcs-v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class TrustedThetaContractError(ValueError):
    """Base error for structural trusted-Theta records."""


class TrustedThetaManifestError(TrustedThetaContractError):
    """Manifest fields or relationships are structurally contradictory."""


class TrustedScorerBindingError(TrustedThetaContractError):
    """A scorer binding contradicts its structural manifest."""


class TrustedResolverResultError(TrustedThetaContractError):
    """A resolver result contradicts its declared state."""


class DigestAlgorithmV1(str, Enum):
    SHA256 = "SHA-256"


class DecimalRoundingPolicyV1(str, Enum):
    """Cross-runtime names; this module never performs rounding."""

    ROUND_UP = "ROUND_UP"
    ROUND_DOWN = "ROUND_DOWN"
    ROUND_CEILING = "ROUND_CEILING"
    ROUND_FLOOR = "ROUND_FLOOR"
    ROUND_HALF_UP = "ROUND_HALF_UP"
    ROUND_HALF_DOWN = "ROUND_HALF_DOWN"
    ROUND_HALF_EVEN = "ROUND_HALF_EVEN"
    ROUND_UNNECESSARY = "ROUND_UNNECESSARY"


class TrustedResolverStateV1(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    NOT_VALID = "NOT_VALID"


class TrustedResolverReasonV1(str, Enum):
    MANIFEST_NOT_AVAILABLE = "MANIFEST_NOT_AVAILABLE"
    TRUST_SNAPSHOT_NOT_AVAILABLE = "TRUST_SNAPSHOT_NOT_AVAILABLE"
    ARTIFACT_NOT_AVAILABLE = "ARTIFACT_NOT_AVAILABLE"
    RUNTIME_DEPENDENCY_NOT_AVAILABLE = "RUNTIME_DEPENDENCY_NOT_AVAILABLE"
    UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"
    TRUST_EVIDENCE_INVALID = "TRUST_EVIDENCE_INVALID"
    TRUST_ENTRY_AMBIGUOUS = "TRUST_ENTRY_AMBIGUOUS"
    THETA_A_MISMATCH = "THETA_A_MISMATCH"
    FEATURE_SCHEMA_MISMATCH = "FEATURE_SCHEMA_MISMATCH"
    MANIFEST_DIGEST_MISMATCH = "MANIFEST_DIGEST_MISMATCH"
    ARTIFACT_DIGEST_MISMATCH = "ARTIFACT_DIGEST_MISMATCH"
    ARTIFACT_SIZE_MISMATCH = "ARTIFACT_SIZE_MISMATCH"
    RUNTIME_INCOMPATIBLE = "RUNTIME_INCOMPATIBLE"
    MANIFEST_REVOKED = "MANIFEST_REVOKED"
    ROLLBACK_DETECTED = "ROLLBACK_DETECTED"
    SUPERSESSION_CONFLICT = "SUPERSESSION_CONFLICT"
    DETERMINISM_POLICY_MISMATCH = "DETERMINISM_POLICY_MISMATCH"


_NOT_READY_REASONS = frozenset(
    {
        TrustedResolverReasonV1.MANIFEST_NOT_AVAILABLE,
        TrustedResolverReasonV1.TRUST_SNAPSHOT_NOT_AVAILABLE,
        TrustedResolverReasonV1.ARTIFACT_NOT_AVAILABLE,
        TrustedResolverReasonV1.RUNTIME_DEPENDENCY_NOT_AVAILABLE,
    }
)
_NOT_VALID_REASONS = frozenset(TrustedResolverReasonV1) - _NOT_READY_REASONS


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value


def _require_optional_text(value: object, name: str) -> str | None:
    if value is not None:
        return _require_text(value, name)
    return None


def _require_nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative non-Boolean integer.")
    return value


def _require_positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive non-Boolean integer.")
    return value


def _require_digest(
    algorithm: object,
    digest: object,
    *,
    algorithm_name: str,
    digest_name: str,
) -> None:
    if algorithm is not DigestAlgorithmV1.SHA256:
        raise ValueError(f"{algorithm_name} must be SHA-256.")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise ValueError(f"{digest_name} must be 64 lowercase hexadecimal characters.")


def _require_unique_text(values: object, name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple of strings.")
    for index, value in enumerate(values):
        _require_text(value, f"{name}[{index}]")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates.")
    return values


def _revalidate_theta(reference: object, error: type[TrustedThetaContractError]) -> None:
    if not isinstance(reference, ConfigurationRefV1):
        raise error("parent_theta_a must be ConfigurationRefV1.")
    try:
        reference.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise error("parent_theta_a failed nested-record validation.") from exc
    if reference.kind is not ConfigurationKind.THETA_A:
        raise error("parent_theta_a must retain the THETA_A configuration kind.")
    if reference.state is not ConfigurationState.READY:
        raise error(
            "The structural manifest requires the upstream Theta_A reference "
            "to be READY; this does not authenticate it."
        )


@dataclass(frozen=True, slots=True)
class TrustedThetaManifestV1:
    """Complete structural description of a future trusted scorer manifest."""

    manifest_id: str
    manifest_version: str
    parent_theta_a: ConfigurationRefV1
    feature_schema_id: str
    feature_schema_version: str
    feature_slot_order: tuple[FeatureSlot, ...]
    missing_policy_id: str
    missing_policy_version: str
    not_applicable_policy_id: str
    not_applicable_policy_version: str
    admission_policy_id: str
    admission_policy_version: str
    scorer_component_id: str
    scorer_component_version: str
    artifact_id: str
    artifact_version: str
    artifact_format: str
    artifact_byte_length: int
    artifact_digest_algorithm: DigestAlgorithmV1
    artifact_digest: str
    canonical_encoding_id: str
    canonical_encoding_version: str
    manifest_digest_algorithm: DigestAlgorithmV1
    manifest_digest: str
    trust_registry_id: str
    trust_registry_version: str
    trust_entry_id: str
    approval_authority_id: str
    approval_record_id: str
    runtime_identifier: str
    runtime_version: str
    abi_identifier: str
    dependency_lock_digest_algorithm: DigestAlgorithmV1
    dependency_lock_digest: str
    deterministic_policy_id: str
    deterministic_policy_version: str
    numeric_precision: int
    numeric_scale: int
    rounding_policy: DecimalRoundingPolicyV1
    compatibility_policy_id: str
    compatibility_policy_version: str
    offline_snapshot_id: str
    offline_snapshot_version: str
    supersedes_manifest_id: str | None = None
    revocation_reference: str | None = None
    schema_id: str = TRUSTED_THETA_MANIFEST_SCHEMA_ID
    schema_version: str = TRUSTED_THETA_MANIFEST_SCHEMA_VERSION
    record_version: str = TRUSTED_THETA_RECORD_VERSION

    def __post_init__(self) -> None:
        error = TrustedThetaManifestError
        try:
            for name in (
                "manifest_id", "manifest_version", "feature_schema_id",
                "feature_schema_version", "missing_policy_id",
                "missing_policy_version", "not_applicable_policy_id",
                "not_applicable_policy_version", "admission_policy_id",
                "admission_policy_version", "scorer_component_id",
                "scorer_component_version", "artifact_id", "artifact_version",
                "artifact_format", "canonical_encoding_id",
                "canonical_encoding_version", "trust_registry_id",
                "trust_registry_version", "trust_entry_id",
                "approval_authority_id", "approval_record_id",
                "runtime_identifier", "runtime_version", "abi_identifier",
                "deterministic_policy_id", "deterministic_policy_version",
                "compatibility_policy_id", "compatibility_policy_version",
                "offline_snapshot_id", "offline_snapshot_version",
            ):
                _require_text(getattr(self, name), name)
            _require_optional_text(self.supersedes_manifest_id, "supersedes_manifest_id")
            _require_optional_text(self.revocation_reference, "revocation_reference")
            _require_positive_integer(self.artifact_byte_length, "artifact_byte_length")
            _require_positive_integer(self.numeric_precision, "numeric_precision")
            _require_nonnegative_integer(self.numeric_scale, "numeric_scale")
        except (TypeError, ValueError) as exc:
            raise error(str(exc)) from exc

        _revalidate_theta(self.parent_theta_a, error)
        if self.schema_id != TRUSTED_THETA_MANIFEST_SCHEMA_ID:
            raise error("Unsupported trusted-Theta manifest schema ID.")
        if self.schema_version != TRUSTED_THETA_MANIFEST_SCHEMA_VERSION:
            raise error("Unsupported trusted-Theta manifest schema version.")
        if self.record_version != TRUSTED_THETA_RECORD_VERSION:
            raise error("Unsupported trusted-Theta record version.")
        if self.feature_schema_id != FEATURE_SCHEMA_ID_V1:
            raise error("feature_schema_id must match the approved seven-slot schema.")
        if self.feature_schema_version != "1":
            raise error("Unsupported feature schema version.")
        if self.feature_slot_order != FEATURE_SLOT_ORDER:
            raise error("feature_slot_order must preserve the exact seven-slot order.")
        if any(not isinstance(slot, FeatureSlot) for slot in self.feature_slot_order):
            raise error("feature_slot_order entries must be FeatureSlot values.")
        if self.canonical_encoding_id != RESTRICTED_CANONICAL_JSON_PROFILE:
            raise error("Unsupported canonical manifest encoding profile.")
        if self.canonical_encoding_version != "1":
            raise error("Unsupported canonical manifest encoding version.")
        if not isinstance(self.rounding_policy, DecimalRoundingPolicyV1):
            raise error("rounding_policy must be DecimalRoundingPolicyV1.")
        try:
            _require_digest(self.artifact_digest_algorithm, self.artifact_digest,
                            algorithm_name="artifact_digest_algorithm", digest_name="artifact_digest")
            _require_digest(self.manifest_digest_algorithm, self.manifest_digest,
                            algorithm_name="manifest_digest_algorithm", digest_name="manifest_digest")
            _require_digest(self.dependency_lock_digest_algorithm, self.dependency_lock_digest,
                            algorithm_name="dependency_lock_digest_algorithm", digest_name="dependency_lock_digest")
        except ValueError as exc:
            raise error(str(exc)) from exc
        if self.supersedes_manifest_id == self.manifest_id:
            raise error("A manifest cannot supersede itself.")


@dataclass(frozen=True, slots=True)
class TrustedScorerBindingV1:
    """Structural link between one manifest and its exact scorer artifact."""

    binding_id: str
    parent_theta_a: ConfigurationRefV1
    manifest_id: str
    manifest_version: str
    manifest_digest_algorithm: DigestAlgorithmV1
    manifest_digest: str
    artifact_id: str
    artifact_version: str
    artifact_byte_length: int
    artifact_digest_algorithm: DigestAlgorithmV1
    artifact_digest: str
    feature_schema_id: str
    feature_schema_version: str
    feature_slot_order: tuple[FeatureSlot, ...]
    scorer_component_id: str
    scorer_component_version: str
    numeric_precision: int
    numeric_scale: int
    rounding_policy: DecimalRoundingPolicyV1
    record_version: str = TRUSTED_THETA_RECORD_VERSION

    def __post_init__(self) -> None:
        error = TrustedScorerBindingError
        try:
            for name in (
                "binding_id", "manifest_id", "manifest_version",
                "artifact_id", "artifact_version", "feature_schema_id",
                "feature_schema_version", "scorer_component_id",
                "scorer_component_version",
            ):
                _require_text(getattr(self, name), name)
            _require_positive_integer(self.artifact_byte_length, "artifact_byte_length")
            _require_positive_integer(self.numeric_precision, "numeric_precision")
            _require_nonnegative_integer(self.numeric_scale, "numeric_scale")
        except (TypeError, ValueError) as exc:
            raise error(str(exc)) from exc
        _revalidate_theta(self.parent_theta_a, error)
        if self.record_version != TRUSTED_THETA_RECORD_VERSION:
            raise error("Unsupported trusted-scorer binding record version.")
        if self.feature_schema_id != FEATURE_SCHEMA_ID_V1:
            raise error("Binding feature schema ID is unsupported.")
        if self.feature_schema_version != "1":
            raise error("Binding feature schema version is unsupported.")
        if self.feature_slot_order != FEATURE_SLOT_ORDER:
            raise error("Binding must preserve the exact seven-slot order.")
        if not isinstance(self.rounding_policy, DecimalRoundingPolicyV1):
            raise error("rounding_policy must be DecimalRoundingPolicyV1.")
        try:
            _require_digest(self.manifest_digest_algorithm, self.manifest_digest,
                            algorithm_name="manifest_digest_algorithm", digest_name="manifest_digest")
            _require_digest(self.artifact_digest_algorithm, self.artifact_digest,
                            algorithm_name="artifact_digest_algorithm", digest_name="artifact_digest")
        except ValueError as exc:
            raise error(str(exc)) from exc

    @classmethod
    def from_manifest(
        cls,
        *,
        binding_id: str,
        manifest: TrustedThetaManifestV1,
    ) -> "TrustedScorerBindingV1":
        if not isinstance(manifest, TrustedThetaManifestV1):
            raise TrustedScorerBindingError("manifest must be TrustedThetaManifestV1.")
        manifest.__post_init__()
        if manifest.revocation_reference is not None:
            raise TrustedScorerBindingError(
                "A structurally revoked manifest cannot produce a READY binding."
            )
        return cls(
            binding_id=binding_id,
            parent_theta_a=manifest.parent_theta_a,
            manifest_id=manifest.manifest_id,
            manifest_version=manifest.manifest_version,
            manifest_digest_algorithm=manifest.manifest_digest_algorithm,
            manifest_digest=manifest.manifest_digest,
            artifact_id=manifest.artifact_id,
            artifact_version=manifest.artifact_version,
            artifact_byte_length=manifest.artifact_byte_length,
            artifact_digest_algorithm=manifest.artifact_digest_algorithm,
            artifact_digest=manifest.artifact_digest,
            feature_schema_id=manifest.feature_schema_id,
            feature_schema_version=manifest.feature_schema_version,
            feature_slot_order=manifest.feature_slot_order,
            scorer_component_id=manifest.scorer_component_id,
            scorer_component_version=manifest.scorer_component_version,
            numeric_precision=manifest.numeric_precision,
            numeric_scale=manifest.numeric_scale,
            rounding_policy=manifest.rounding_policy,
        )


def _binding_matches_manifest(
    binding: TrustedScorerBindingV1,
    manifest: TrustedThetaManifestV1,
) -> bool:
    expected = TrustedScorerBindingV1.from_manifest(
        binding_id=binding.binding_id,
        manifest=manifest,
    )
    return binding == expected


@dataclass(frozen=True, slots=True)
class TrustedScorerResolverResultV1:
    """Structural resolver result; no actual resolution occurs here."""

    resolver_result_id: str
    resolver_component_id: str
    resolver_component_version: str
    state: TrustedResolverStateV1
    reason: TrustedResolverReasonV1 | None
    retryable: bool
    parent_theta_a: ConfigurationRefV1
    registry_snapshot_id: str | None
    registry_snapshot_version: str | None
    registry_snapshot_digest_algorithm: DigestAlgorithmV1 | None
    registry_snapshot_digest: str | None
    manifest: TrustedThetaManifestV1 | None
    binding: TrustedScorerBindingV1 | None
    runtime_fingerprint: str | None
    evidence_references: tuple[str, ...]
    record_version: str = TRUSTED_THETA_RECORD_VERSION

    def __post_init__(self) -> None:
        error = TrustedResolverResultError
        try:
            _require_text(self.resolver_result_id, "resolver_result_id")
            _require_text(self.resolver_component_id, "resolver_component_id")
            _require_text(self.resolver_component_version, "resolver_component_version")
            _require_optional_text(self.registry_snapshot_id, "registry_snapshot_id")
            _require_optional_text(self.registry_snapshot_version, "registry_snapshot_version")
            _require_optional_text(self.registry_snapshot_digest, "registry_snapshot_digest")
            _require_optional_text(self.runtime_fingerprint, "runtime_fingerprint")
            _require_unique_text(self.evidence_references, "evidence_references")
        except (TypeError, ValueError) as exc:
            raise error(str(exc)) from exc
        _revalidate_theta(self.parent_theta_a, error)
        if self.record_version != TRUSTED_THETA_RECORD_VERSION:
            raise error("Unsupported trusted resolver-result version.")
        if not isinstance(self.state, TrustedResolverStateV1):
            raise error("state must be TrustedResolverStateV1.")
        if self.reason is not None and not isinstance(self.reason, TrustedResolverReasonV1):
            raise error("reason must be TrustedResolverReasonV1 or null.")
        if not isinstance(self.retryable, bool):
            raise error("retryable must be Boolean.")

        snapshot_values = (
            self.registry_snapshot_id,
            self.registry_snapshot_version,
            self.registry_snapshot_digest_algorithm,
            self.registry_snapshot_digest,
        )
        if any(value is not None for value in snapshot_values):
            if any(value is None for value in snapshot_values):
                raise error("Registry snapshot metadata must be wholly present or null.")
            try:
                _require_digest(self.registry_snapshot_digest_algorithm,
                                self.registry_snapshot_digest,
                                algorithm_name="registry_snapshot_digest_algorithm",
                                digest_name="registry_snapshot_digest")
            except ValueError as exc:
                raise error(str(exc)) from exc

        if self.manifest is not None:
            if not isinstance(self.manifest, TrustedThetaManifestV1):
                raise error("manifest must be TrustedThetaManifestV1 or null.")
            self.manifest.__post_init__()
            if self.manifest.parent_theta_a != self.parent_theta_a:
                raise error("Resolver manifest Theta_A differs from the source Theta_A.")
        if self.binding is not None:
            if not isinstance(self.binding, TrustedScorerBindingV1):
                raise error("binding must be TrustedScorerBindingV1 or null.")
            self.binding.__post_init__()
            if self.binding.parent_theta_a != self.parent_theta_a:
                raise error("Resolver binding Theta_A differs from the source Theta_A.")

        if self.state is TrustedResolverStateV1.READY:
            if self.reason is not None:
                raise error("READY has no failure reason.")
            if self.retryable:
                raise error("READY cannot be retryable.")
            if any(value is None for value in snapshot_values):
                raise error("READY requires complete registry snapshot metadata.")
            if self.manifest is None or self.binding is None:
                raise error("READY requires a manifest and exact scorer binding.")
            if (
                self.registry_snapshot_id != self.manifest.offline_snapshot_id
                or self.registry_snapshot_version
                != self.manifest.offline_snapshot_version
            ):
                raise error(
                    "READY registry snapshot identity differs from the manifest's "
                    "pinned offline snapshot."
                )
            if self.runtime_fingerprint is None:
                raise error("READY requires a runtime fingerprint.")
            if not self.evidence_references:
                raise error("READY requires structural verification references.")
            if self.manifest.revocation_reference is not None:
                raise error("READY cannot reference a structurally revoked manifest.")
            try:
                matches = _binding_matches_manifest(self.binding, self.manifest)
            except TrustedThetaContractError as exc:
                raise error("READY binding could not be matched to its manifest.") from exc
            if not matches:
                raise error("READY binding does not match the structural manifest.")
        elif self.state is TrustedResolverStateV1.NOT_READY:
            if self.reason not in _NOT_READY_REASONS:
                raise error("NOT_READY requires an approved missing-prerequisite reason.")
            if not self.retryable:
                raise error("NOT_READY must be marked retryable.")
            if self.binding is not None:
                raise error("NOT_READY cannot carry a trusted scorer binding.")
            if self.reason is TrustedResolverReasonV1.TRUST_SNAPSHOT_NOT_AVAILABLE:
                if any(value is not None for value in snapshot_values):
                    raise error(
                        "TRUST_SNAPSHOT_NOT_AVAILABLE requires null snapshot metadata."
                    )
                if self.manifest is not None:
                    raise error(
                        "TRUST_SNAPSHOT_NOT_AVAILABLE cannot claim a resolved manifest."
                    )
            elif self.reason is TrustedResolverReasonV1.MANIFEST_NOT_AVAILABLE:
                if any(value is None for value in snapshot_values):
                    raise error(
                        "MANIFEST_NOT_AVAILABLE requires the complete registry snapshot."
                    )
                if self.manifest is not None:
                    raise error("MANIFEST_NOT_AVAILABLE requires manifest=null.")
            else:
                if any(value is None for value in snapshot_values):
                    raise error(
                        "Artifact/runtime NOT_READY requires the complete registry snapshot."
                    )
                if self.manifest is None:
                    raise error(
                        "Artifact/runtime NOT_READY requires the structural manifest."
                    )
                if (
                    self.registry_snapshot_id != self.manifest.offline_snapshot_id
                    or self.registry_snapshot_version
                    != self.manifest.offline_snapshot_version
                ):
                    raise error(
                        "NOT_READY registry snapshot identity differs from the "
                        "manifest's pinned offline snapshot."
                    )
        else:
            if self.reason not in _NOT_VALID_REASONS:
                raise error("NOT_VALID requires an approved contradiction reason.")
            if self.retryable:
                raise error("NOT_VALID cannot be marked retryable.")
            if self.binding is not None:
                raise error("NOT_VALID cannot carry a trusted scorer binding.")
            if not self.evidence_references:
                raise error("NOT_VALID requires structural contradiction evidence.")


__all__ = [
    "RESTRICTED_CANONICAL_JSON_PROFILE",
    "TRUSTED_THETA_MANIFEST_SCHEMA_ID",
    "TRUSTED_THETA_MANIFEST_SCHEMA_VERSION",
    "TRUSTED_THETA_RECORD_VERSION",
    "DecimalRoundingPolicyV1",
    "DigestAlgorithmV1",
    "TrustedResolverReasonV1",
    "TrustedResolverResultError",
    "TrustedResolverStateV1",
    "TrustedScorerBindingError",
    "TrustedScorerBindingV1",
    "TrustedScorerResolverResultV1",
    "TrustedThetaContractError",
    "TrustedThetaManifestError",
    "TrustedThetaManifestV1",
]
