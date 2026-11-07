"""Strict public codec for structural scoring evidence V2.

The wire format preserves immutable public source content and ordering.  It
cannot recreate Python object identity, so decoding a scoring operation also
requires the exact live :class:`ScoringSourceSnapshotV2` to which the payload
claims to be bound.

Canonical encoding is a deliberately restricted RFC 8785/JCS-compatible
subset: objects have ASCII keys, arrays preserve order, integers are limited
to the interoperable IEEE-754 safe range, and floating-point JSON numbers are
not supported.  Evidence Decimals are encoded as strings under the manifest's
explicit precision and scale.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping, NoReturn

from pipeline.proposed.contracts import (
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    FeatureSlot,
)
from pipeline.proposed.feature_construction import (
    CandidateFeatureVectorV0,
    FeatureSlotValueV0,
)
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintResultV2,
    constraint_result_v2_to_json,
)
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
    ScoringOperationResultV2,
    ScoringSourceSnapshotV2,
)
from pipeline.proposed.trusted_theta_contracts_v1 import (
    DecimalRoundingPolicyV1,
    DigestAlgorithmV1,
    TrustedResolverReasonV1,
    TrustedResolverStateV1,
    TrustedScorerBindingV1,
    TrustedScorerResolverResultV1,
    TrustedThetaManifestV1,
)


SCORING_CODEC_SCHEMA_ID = "pantryproof.scoring-evidence"
SCORING_CODEC_SCHEMA_VERSION = 2
SCORING_CODEC_VERSION = "scoring-codec-v2"

_SAFE_INTEGER = (1 << 53) - 1
_ASCII_KEY_RE = re.compile(r"^[\x20-\x7e]+$")
_DOMAIN_RE = re.compile(r"^[a-z][a-z0-9.-]*\.v[0-9]+$")


class ScoringCodecError(ValueError):
    """Serialized scoring evidence is malformed or unsupported."""


class ScoringCodecSourceBindingError(ScoringCodecError):
    """A payload does not match the exact supplied live source snapshot."""


def _fail(message: str) -> NoReturn:
    raise ScoringCodecError(message)


def _validate_supported_json(value: Any, path: str = "$" ) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not -_SAFE_INTEGER <= value <= _SAFE_INTEGER:
            _fail(f"{path} integer is outside the interoperable safe range.")
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ScoringCodecError(f"{path} contains an invalid Unicode scalar.") from exc
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_supported_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not _ASCII_KEY_RE.fullmatch(key):
                _fail(f"{path} object keys must be printable ASCII strings.")
            _validate_supported_json(item, f"{path}.{key}")
        return
    _fail(f"{path} contains unsupported JSON value type {type(value).__name__}.")


def canonical_json_bytes(value: Any) -> bytes:
    """Encode the supported JSON subset into deterministic UTF-8 bytes."""

    _validate_supported_json(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ScoringCodecError("Canonical JSON encoding failed.") from exc


def _reject_float(_value: str) -> NoReturn:
    _fail("JSON floating-point numbers are not permitted.")


def _reject_constant(_value: str) -> NoReturn:
    _fail("Non-finite JSON constants are not permitted.")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"Duplicate JSON object key is not permitted: {key!r}.")
        result[key] = value
    return result


def parse_canonical_json_bytes(payload: bytes) -> Any:
    """Parse and require exact canonical bytes for the supported JSON subset."""

    if not isinstance(payload, bytes) or not payload:
        _fail("payload must be nonempty bytes.")
    if payload.startswith(b"\xef\xbb\xbf"):
        _fail("UTF-8 BOM is not permitted.")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ScoringCodecError("payload is not valid UTF-8.") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except ScoringCodecError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ScoringCodecError("payload is not valid scoring JSON.") from exc
    _validate_supported_json(value)
    if canonical_json_bytes(value) != payload:
        _fail("payload is not in the required canonical JSON byte form.")
    return value


def _validate_decimal_policy(*, precision: int, scale: int) -> None:
    if isinstance(precision, bool) or not isinstance(precision, int) or precision < 1:
        _fail("precision must be a positive non-Boolean integer.")
    if isinstance(scale, bool) or not isinstance(scale, int) or scale < 0:
        _fail("scale must be a nonnegative non-Boolean integer.")


def _decimal_pattern(scale: int) -> re.Pattern[str]:
    if scale == 0:
        return re.compile(r"^(?:0|-?[1-9][0-9]*)$")
    return re.compile(rf"^-?(?:0|[1-9][0-9]*)\.[0-9]{{{scale}}}$")


def parse_canonical_decimal(
    value: object,
    *,
    precision: int,
    scale: int,
) -> Decimal:
    """Parse an exact fixed-scale finite Decimal string without rounding."""

    _validate_decimal_policy(precision=precision, scale=scale)
    if not isinstance(value, str) or not _decimal_pattern(scale).fullmatch(value):
        _fail("raw_score is not a canonical fixed-scale Decimal string.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ScoringCodecError("raw_score is not a valid Decimal.") from exc
    if not parsed.is_finite():
        _fail("raw_score must be finite.")
    if parsed.is_zero() and parsed.is_signed():
        _fail("negative zero is not permitted.")
    digits = value.lstrip("-").replace(".", "").lstrip("0")
    significant_digits = len(digits) if digits else 1
    if significant_digits > precision:
        _fail("raw_score exceeds the manifest precision.")
    if parsed.as_tuple().exponent != -scale:
        _fail("raw_score has an incorrect Decimal scale.")
    return parsed


def canonical_decimal_string(
    value: Decimal,
    *,
    precision: int,
    scale: int,
) -> str:
    """Validate and encode an already-quantized Decimal without rounding it."""

    _validate_decimal_policy(precision=precision, scale=scale)
    if not isinstance(value, Decimal) or not value.is_finite():
        _fail("raw_score must be a finite Decimal.")
    if value.is_zero() and value.is_signed():
        _fail("negative zero is not permitted.")
    text = format(value, "f")
    parsed = parse_canonical_decimal(text, precision=precision, scale=scale)
    if parsed.as_tuple() != value.as_tuple():
        _fail("raw_score would require normalization or silent rounding.")
    return text


def deterministic_content_id(
    domain: str,
    public_record: Mapping[str, Any],
    *,
    id_field: str,
) -> str:
    """Hash canonical content with explicit domain separation.

    The record ID is removed from the digest preimage.  The digest is content
    integrity metadata, not approval, signature, or source authentication.
    """

    if not isinstance(domain, str) or not _DOMAIN_RE.fullmatch(domain):
        _fail("domain must be a lowercase versioned identifier.")
    if not isinstance(public_record, Mapping):
        _fail("public_record must be a mapping.")
    if not isinstance(id_field, str) or id_field not in public_record:
        _fail("id_field must name an explicit record key.")
    preimage = dict(public_record)
    del preimage[id_field]
    digest = hashlib.sha256(
        domain.encode("ascii") + b"\x00" + canonical_json_bytes(preimage)
    ).hexdigest()
    return f"{domain}:sha256:{digest}"


def _object(value: Any, keys: tuple[str, ...], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{name} must be a JSON object.")
    actual = set(value)
    expected = set(keys)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        _fail(f"{name} keys differ; missing={missing}, extra={extra}.")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{name} must be a nonempty string.")
    return value


def _optional_text(value: Any, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{name} must be a non-Boolean integer >= {minimum}.")
    return value


def _array(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{name} must be a JSON array.")
    return value


def _enum(value: Any, enum_type: type[Enum], name: str) -> Any:
    if not isinstance(value, str):
        _fail(f"{name} must be a string enum value.")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ScoringCodecError(f"{name} has an unsupported value.") from exc


def _configuration(value: ConfigurationRefV1) -> dict[str, Any]:
    return {
        "configuration_id": value.configuration_id,
        "configuration_version": value.configuration_version,
        "content_hash": value.content_hash,
        "kind": value.kind.value,
        "record_version": value.record_version,
        "state": value.state.value,
        "status_reason": value.status_reason,
    }


def _slot(slot: FeatureSlotValueV0) -> dict[str, Any]:
    raw_value: str | None
    if isinstance(slot.value, Decimal):
        if not slot.value.is_finite():
            _fail("Feature-slot Decimal values must be finite.")
        raw_value = str(slot.value)
    else:
        raw_value = slot.value
    return {
        "availability": slot.availability.value,
        "provenance_references": list(slot.provenance_references),
        "reason": None if slot.reason is None else slot.reason.value,
        "record_version": slot.record_version,
        "slot": slot.slot.value,
        "value": raw_value,
    }


def _feature_vector(vector: CandidateFeatureVectorV0) -> dict[str, Any]:
    return {
        "candidate_id": vector.candidate.candidate_id,
        "constraint_result_id": vector.constraint_result.constraint_result_id,
        "feature_schema_id": vector.feature_schema_id,
        "record_version": vector.record_version,
        "slot_values": [_slot(slot) for slot in vector.slot_values],
        "theta_a_reference": _configuration(vector.theta_a_reference),
    }


def _constraint(result: ConstraintResultV2) -> dict[str, Any]:
    return json.loads(constraint_result_v2_to_json(result))


def _source_snapshot(snapshot: ScoringSourceSnapshotV2) -> dict[str, Any]:
    return {
        "c0_candidate_id": snapshot.c0_candidate.candidate_id,
        "candidate_ids": [candidate.candidate_id for candidate in snapshot.candidates],
        "component_version": snapshot.component_version,
        "constraint_results": [_constraint(result) for result in snapshot.constraint_results],
        "feature_vectors": [_feature_vector(vector) for vector in snapshot.candidate_features],
        "field_id": snapshot.field_id,
        "receipt_id": snapshot.receipt_id,
        "record_version": snapshot.record_version,
        "source_component_versions": list(snapshot.source_component_versions),
        "source_snapshot_id": snapshot.source_snapshot_id,
        "theta_a_reference": _configuration(snapshot.theta_a_reference),
    }


# The remaining explicit record mappings are defined below the structural
# contracts.  Keeping these mappings handwritten is intentional: generic
# dataclass serialization could leak capture-once identity metadata.


def _configuration_from_json(value: Any) -> ConfigurationRefV1:
    data = _object(
        value,
        (
            "configuration_id",
            "configuration_version",
            "content_hash",
            "kind",
            "record_version",
            "state",
            "status_reason",
        ),
        "ConfigurationRefV1",
    )
    return ConfigurationRefV1(
        kind=_enum(data["kind"], ConfigurationKind, "kind"),
        configuration_id=_text(data["configuration_id"], "configuration_id"),
        configuration_version=_text(
            data["configuration_version"], "configuration_version"
        ),
        state=_enum(data["state"], ConfigurationState, "state"),
        content_hash=_optional_text(data["content_hash"], "content_hash"),
        status_reason=_optional_text(data["status_reason"], "status_reason"),
        record_version=_text(data["record_version"], "record_version"),
    )


def _manifest(manifest: TrustedThetaManifestV1) -> dict[str, Any]:
    manifest.__post_init__()
    return {
        "abi_identifier": manifest.abi_identifier,
        "admission_policy_id": manifest.admission_policy_id,
        "admission_policy_version": manifest.admission_policy_version,
        "approval_authority_id": manifest.approval_authority_id,
        "approval_record_id": manifest.approval_record_id,
        "artifact_byte_length": manifest.artifact_byte_length,
        "artifact_digest": manifest.artifact_digest,
        "artifact_digest_algorithm": manifest.artifact_digest_algorithm.value,
        "artifact_format": manifest.artifact_format,
        "artifact_id": manifest.artifact_id,
        "artifact_version": manifest.artifact_version,
        "canonical_encoding_id": manifest.canonical_encoding_id,
        "canonical_encoding_version": manifest.canonical_encoding_version,
        "compatibility_policy_id": manifest.compatibility_policy_id,
        "compatibility_policy_version": manifest.compatibility_policy_version,
        "dependency_lock_digest": manifest.dependency_lock_digest,
        "dependency_lock_digest_algorithm": (
            manifest.dependency_lock_digest_algorithm.value
        ),
        "deterministic_policy_id": manifest.deterministic_policy_id,
        "deterministic_policy_version": manifest.deterministic_policy_version,
        "feature_schema_id": manifest.feature_schema_id,
        "feature_schema_version": manifest.feature_schema_version,
        "feature_slot_order": [slot.value for slot in manifest.feature_slot_order],
        "manifest_digest": manifest.manifest_digest,
        "manifest_digest_algorithm": manifest.manifest_digest_algorithm.value,
        "manifest_id": manifest.manifest_id,
        "manifest_version": manifest.manifest_version,
        "missing_policy_id": manifest.missing_policy_id,
        "missing_policy_version": manifest.missing_policy_version,
        "not_applicable_policy_id": manifest.not_applicable_policy_id,
        "not_applicable_policy_version": manifest.not_applicable_policy_version,
        "numeric_precision": manifest.numeric_precision,
        "numeric_scale": manifest.numeric_scale,
        "offline_snapshot_id": manifest.offline_snapshot_id,
        "offline_snapshot_version": manifest.offline_snapshot_version,
        "parent_theta_a": _configuration(manifest.parent_theta_a),
        "record_version": manifest.record_version,
        "revocation_reference": manifest.revocation_reference,
        "rounding_policy": manifest.rounding_policy.value,
        "runtime_identifier": manifest.runtime_identifier,
        "runtime_version": manifest.runtime_version,
        "schema_id": manifest.schema_id,
        "schema_version": manifest.schema_version,
        "scorer_component_id": manifest.scorer_component_id,
        "scorer_component_version": manifest.scorer_component_version,
        "supersedes_manifest_id": manifest.supersedes_manifest_id,
        "trust_entry_id": manifest.trust_entry_id,
        "trust_registry_id": manifest.trust_registry_id,
        "trust_registry_version": manifest.trust_registry_version,
    }


_MANIFEST_KEYS = (
    "abi_identifier", "admission_policy_id", "admission_policy_version",
    "approval_authority_id", "approval_record_id", "artifact_byte_length",
    "artifact_digest", "artifact_digest_algorithm", "artifact_format",
    "artifact_id", "artifact_version", "canonical_encoding_id",
    "canonical_encoding_version", "compatibility_policy_id",
    "compatibility_policy_version", "dependency_lock_digest",
    "dependency_lock_digest_algorithm", "deterministic_policy_id",
    "deterministic_policy_version", "feature_schema_id",
    "feature_schema_version", "feature_slot_order", "manifest_digest",
    "manifest_digest_algorithm", "manifest_id", "manifest_version",
    "missing_policy_id", "missing_policy_version", "not_applicable_policy_id",
    "not_applicable_policy_version", "numeric_precision", "numeric_scale",
    "offline_snapshot_id", "offline_snapshot_version", "parent_theta_a",
    "record_version", "revocation_reference", "rounding_policy",
    "runtime_identifier", "runtime_version", "schema_id", "schema_version",
    "scorer_component_id", "scorer_component_version",
    "supersedes_manifest_id", "trust_entry_id", "trust_registry_id",
    "trust_registry_version",
)


def _manifest_from_json(value: Any) -> TrustedThetaManifestV1:
    data = _object(value, _MANIFEST_KEYS, "TrustedThetaManifestV1")
    return TrustedThetaManifestV1(
        manifest_id=_text(data["manifest_id"], "manifest_id"),
        manifest_version=_text(data["manifest_version"], "manifest_version"),
        parent_theta_a=_configuration_from_json(data["parent_theta_a"]),
        feature_schema_id=_text(data["feature_schema_id"], "feature_schema_id"),
        feature_schema_version=_text(
            data["feature_schema_version"], "feature_schema_version"
        ),
        feature_slot_order=tuple(
            _enum(item, FeatureSlot, "feature_slot_order item")
            for item in _array(data["feature_slot_order"], "feature_slot_order")
        ),
        missing_policy_id=_text(data["missing_policy_id"], "missing_policy_id"),
        missing_policy_version=_text(
            data["missing_policy_version"], "missing_policy_version"
        ),
        not_applicable_policy_id=_text(
            data["not_applicable_policy_id"], "not_applicable_policy_id"
        ),
        not_applicable_policy_version=_text(
            data["not_applicable_policy_version"],
            "not_applicable_policy_version",
        ),
        admission_policy_id=_text(
            data["admission_policy_id"], "admission_policy_id"
        ),
        admission_policy_version=_text(
            data["admission_policy_version"], "admission_policy_version"
        ),
        scorer_component_id=_text(
            data["scorer_component_id"], "scorer_component_id"
        ),
        scorer_component_version=_text(
            data["scorer_component_version"], "scorer_component_version"
        ),
        artifact_id=_text(data["artifact_id"], "artifact_id"),
        artifact_version=_text(data["artifact_version"], "artifact_version"),
        artifact_format=_text(data["artifact_format"], "artifact_format"),
        artifact_byte_length=_integer(
            data["artifact_byte_length"], "artifact_byte_length", minimum=1
        ),
        artifact_digest_algorithm=_enum(
            data["artifact_digest_algorithm"],
            DigestAlgorithmV1,
            "artifact_digest_algorithm",
        ),
        artifact_digest=_text(data["artifact_digest"], "artifact_digest"),
        canonical_encoding_id=_text(
            data["canonical_encoding_id"], "canonical_encoding_id"
        ),
        canonical_encoding_version=_text(
            data["canonical_encoding_version"], "canonical_encoding_version"
        ),
        manifest_digest_algorithm=_enum(
            data["manifest_digest_algorithm"],
            DigestAlgorithmV1,
            "manifest_digest_algorithm",
        ),
        manifest_digest=_text(data["manifest_digest"], "manifest_digest"),
        trust_registry_id=_text(data["trust_registry_id"], "trust_registry_id"),
        trust_registry_version=_text(
            data["trust_registry_version"], "trust_registry_version"
        ),
        trust_entry_id=_text(data["trust_entry_id"], "trust_entry_id"),
        approval_authority_id=_text(
            data["approval_authority_id"], "approval_authority_id"
        ),
        approval_record_id=_text(
            data["approval_record_id"], "approval_record_id"
        ),
        runtime_identifier=_text(data["runtime_identifier"], "runtime_identifier"),
        runtime_version=_text(data["runtime_version"], "runtime_version"),
        abi_identifier=_text(data["abi_identifier"], "abi_identifier"),
        dependency_lock_digest_algorithm=_enum(
            data["dependency_lock_digest_algorithm"],
            DigestAlgorithmV1,
            "dependency_lock_digest_algorithm",
        ),
        dependency_lock_digest=_text(
            data["dependency_lock_digest"], "dependency_lock_digest"
        ),
        deterministic_policy_id=_text(
            data["deterministic_policy_id"], "deterministic_policy_id"
        ),
        deterministic_policy_version=_text(
            data["deterministic_policy_version"],
            "deterministic_policy_version",
        ),
        numeric_precision=_integer(
            data["numeric_precision"], "numeric_precision", minimum=1
        ),
        numeric_scale=_integer(data["numeric_scale"], "numeric_scale"),
        rounding_policy=_enum(
            data["rounding_policy"], DecimalRoundingPolicyV1, "rounding_policy"
        ),
        compatibility_policy_id=_text(
            data["compatibility_policy_id"], "compatibility_policy_id"
        ),
        compatibility_policy_version=_text(
            data["compatibility_policy_version"],
            "compatibility_policy_version",
        ),
        offline_snapshot_id=_text(
            data["offline_snapshot_id"], "offline_snapshot_id"
        ),
        offline_snapshot_version=_text(
            data["offline_snapshot_version"], "offline_snapshot_version"
        ),
        supersedes_manifest_id=_optional_text(
            data["supersedes_manifest_id"], "supersedes_manifest_id"
        ),
        revocation_reference=_optional_text(
            data["revocation_reference"], "revocation_reference"
        ),
        schema_id=_text(data["schema_id"], "schema_id"),
        schema_version=_text(data["schema_version"], "schema_version"),
        record_version=_text(data["record_version"], "record_version"),
    )


def _binding(binding: TrustedScorerBindingV1) -> dict[str, Any]:
    binding.__post_init__()
    return {
        "artifact_byte_length": binding.artifact_byte_length,
        "artifact_digest": binding.artifact_digest,
        "artifact_digest_algorithm": binding.artifact_digest_algorithm.value,
        "artifact_id": binding.artifact_id,
        "artifact_version": binding.artifact_version,
        "binding_id": binding.binding_id,
        "feature_schema_id": binding.feature_schema_id,
        "feature_schema_version": binding.feature_schema_version,
        "feature_slot_order": [slot.value for slot in binding.feature_slot_order],
        "manifest_digest": binding.manifest_digest,
        "manifest_digest_algorithm": binding.manifest_digest_algorithm.value,
        "manifest_id": binding.manifest_id,
        "manifest_version": binding.manifest_version,
        "numeric_precision": binding.numeric_precision,
        "numeric_scale": binding.numeric_scale,
        "parent_theta_a": _configuration(binding.parent_theta_a),
        "record_version": binding.record_version,
        "rounding_policy": binding.rounding_policy.value,
        "scorer_component_id": binding.scorer_component_id,
        "scorer_component_version": binding.scorer_component_version,
    }


_BINDING_KEYS = (
    "artifact_byte_length", "artifact_digest", "artifact_digest_algorithm",
    "artifact_id", "artifact_version", "binding_id", "feature_schema_id",
    "feature_schema_version", "feature_slot_order", "manifest_digest",
    "manifest_digest_algorithm", "manifest_id", "manifest_version",
    "numeric_precision", "numeric_scale", "parent_theta_a", "record_version",
    "rounding_policy", "scorer_component_id", "scorer_component_version",
)


def _binding_from_json(value: Any) -> TrustedScorerBindingV1:
    data = _object(value, _BINDING_KEYS, "TrustedScorerBindingV1")
    return TrustedScorerBindingV1(
        binding_id=_text(data["binding_id"], "binding_id"),
        parent_theta_a=_configuration_from_json(data["parent_theta_a"]),
        manifest_id=_text(data["manifest_id"], "manifest_id"),
        manifest_version=_text(data["manifest_version"], "manifest_version"),
        manifest_digest_algorithm=_enum(
            data["manifest_digest_algorithm"],
            DigestAlgorithmV1,
            "manifest_digest_algorithm",
        ),
        manifest_digest=_text(data["manifest_digest"], "manifest_digest"),
        artifact_id=_text(data["artifact_id"], "artifact_id"),
        artifact_version=_text(data["artifact_version"], "artifact_version"),
        artifact_byte_length=_integer(
            data["artifact_byte_length"], "artifact_byte_length", minimum=1
        ),
        artifact_digest_algorithm=_enum(
            data["artifact_digest_algorithm"],
            DigestAlgorithmV1,
            "artifact_digest_algorithm",
        ),
        artifact_digest=_text(data["artifact_digest"], "artifact_digest"),
        feature_schema_id=_text(data["feature_schema_id"], "feature_schema_id"),
        feature_schema_version=_text(
            data["feature_schema_version"], "feature_schema_version"
        ),
        feature_slot_order=tuple(
            _enum(item, FeatureSlot, "feature_slot_order item")
            for item in _array(data["feature_slot_order"], "feature_slot_order")
        ),
        scorer_component_id=_text(
            data["scorer_component_id"], "scorer_component_id"
        ),
        scorer_component_version=_text(
            data["scorer_component_version"], "scorer_component_version"
        ),
        numeric_precision=_integer(
            data["numeric_precision"], "numeric_precision", minimum=1
        ),
        numeric_scale=_integer(data["numeric_scale"], "numeric_scale"),
        rounding_policy=_enum(
            data["rounding_policy"], DecimalRoundingPolicyV1, "rounding_policy"
        ),
        record_version=_text(data["record_version"], "record_version"),
    )


def _resolver(result: TrustedScorerResolverResultV1) -> dict[str, Any]:
    result.__post_init__()
    return {
        "binding": None if result.binding is None else _binding(result.binding),
        "evidence_references": list(result.evidence_references),
        "manifest": None if result.manifest is None else _manifest(result.manifest),
        "parent_theta_a": _configuration(result.parent_theta_a),
        "reason": None if result.reason is None else result.reason.value,
        "record_version": result.record_version,
        "registry_snapshot_digest": result.registry_snapshot_digest,
        "registry_snapshot_digest_algorithm": (
            None
            if result.registry_snapshot_digest_algorithm is None
            else result.registry_snapshot_digest_algorithm.value
        ),
        "registry_snapshot_id": result.registry_snapshot_id,
        "registry_snapshot_version": result.registry_snapshot_version,
        "resolver_component_id": result.resolver_component_id,
        "resolver_component_version": result.resolver_component_version,
        "resolver_result_id": result.resolver_result_id,
        "retryable": result.retryable,
        "runtime_fingerprint": result.runtime_fingerprint,
        "state": result.state.value,
    }


_RESOLVER_KEYS = (
    "binding", "evidence_references", "manifest", "parent_theta_a", "reason",
    "record_version", "registry_snapshot_digest",
    "registry_snapshot_digest_algorithm", "registry_snapshot_id",
    "registry_snapshot_version", "resolver_component_id",
    "resolver_component_version", "resolver_result_id", "retryable",
    "runtime_fingerprint", "state",
)


def _resolver_from_json(
    value: Any,
    *,
    exact_binding: TrustedScorerBindingV1 | None = None,
) -> TrustedScorerResolverResultV1:
    data = _object(value, _RESOLVER_KEYS, "TrustedScorerResolverResultV1")
    encoded_binding = data["binding"]
    if exact_binding is None:
        binding = None if encoded_binding is None else _binding_from_json(encoded_binding)
    else:
        if encoded_binding != _binding(exact_binding):
            raise ScoringCodecSourceBindingError(
                "Resolver binding differs from the exact aggregate binding."
            )
        binding = exact_binding
    return TrustedScorerResolverResultV1(
        resolver_result_id=_text(data["resolver_result_id"], "resolver_result_id"),
        resolver_component_id=_text(
            data["resolver_component_id"], "resolver_component_id"
        ),
        resolver_component_version=_text(
            data["resolver_component_version"], "resolver_component_version"
        ),
        state=_enum(data["state"], TrustedResolverStateV1, "state"),
        reason=(
            None
            if data["reason"] is None
            else _enum(data["reason"], TrustedResolverReasonV1, "reason")
        ),
        retryable=data["retryable"],
        parent_theta_a=_configuration_from_json(data["parent_theta_a"]),
        registry_snapshot_id=_optional_text(
            data["registry_snapshot_id"], "registry_snapshot_id"
        ),
        registry_snapshot_version=_optional_text(
            data["registry_snapshot_version"], "registry_snapshot_version"
        ),
        registry_snapshot_digest_algorithm=(
            None
            if data["registry_snapshot_digest_algorithm"] is None
            else _enum(
                data["registry_snapshot_digest_algorithm"],
                DigestAlgorithmV1,
                "registry_snapshot_digest_algorithm",
            )
        ),
        registry_snapshot_digest=_optional_text(
            data["registry_snapshot_digest"], "registry_snapshot_digest"
        ),
        manifest=(
            None if data["manifest"] is None else _manifest_from_json(data["manifest"])
        ),
        binding=binding,
        runtime_fingerprint=_optional_text(
            data["runtime_fingerprint"], "runtime_fingerprint"
        ),
        evidence_references=tuple(
            _text(item, "evidence_references item")
            for item in _array(data["evidence_references"], "evidence_references")
        ),
        record_version=_text(data["record_version"], "record_version"),
    )


def expected_source_snapshot_id(snapshot: ScoringSourceSnapshotV2) -> str:
    return deterministic_content_id(
        "pantryproof.scoring-source-snapshot.v2",
        _source_snapshot(snapshot),
        id_field="source_snapshot_id",
    )


def _admission(admission: PreScoreAdmissionEvidenceV2) -> dict[str, Any]:
    admission.__post_init__()
    return {
        "admission_id": admission.admission_id,
        "candidate_id": admission.candidate.candidate_id,
        "component_id": admission.component_id,
        "component_version": admission.component_version,
        "constraint_result_id": admission.constraint_result.constraint_result_id,
        "evidence_references": list(admission.evidence_references),
        "feature_vector_candidate_id": (
            None
            if admission.feature_vector is None
            else admission.feature_vector.candidate.candidate_id
        ),
        "policy_id": admission.policy_id,
        "policy_version": admission.policy_version,
        "record_version": admission.record_version,
        "source_snapshot_id": admission.source_snapshot_id,
        "state": admission.state.value,
    }


_ADMISSION_KEYS = (
    "admission_id", "candidate_id", "component_id", "component_version",
    "constraint_result_id", "evidence_references", "feature_vector_candidate_id",
    "policy_id", "policy_version", "record_version", "source_snapshot_id", "state",
)


def expected_admission_id(admission: PreScoreAdmissionEvidenceV2) -> str:
    return deterministic_content_id(
        "pantryproof.pre-score-admission.v2",
        _admission(admission),
        id_field="admission_id",
    )


def _find_source_members(
    snapshot: ScoringSourceSnapshotV2,
    *,
    candidate_id: str,
    constraint_result_id: str,
    feature_vector_candidate_id: str | None,
) -> tuple[Any, ConstraintResultV2, CandidateFeatureVectorV0 | None]:
    candidates = [item for item in snapshot.candidates if item.candidate_id == candidate_id]
    if len(candidates) != 1:
        raise ScoringCodecSourceBindingError(
            "Admission candidate does not resolve exactly once in the live source."
        )
    results = [
        item
        for item in snapshot.constraint_results
        if item.constraint_result_id == constraint_result_id
    ]
    if len(results) != 1:
        raise ScoringCodecSourceBindingError(
            "Admission V2 result does not resolve exactly once in the live source."
        )
    if feature_vector_candidate_id is None:
        vector = None
    else:
        vectors = [
            item
            for item in snapshot.candidate_features
            if item.candidate.candidate_id == feature_vector_candidate_id
        ]
        if len(vectors) != 1:
            raise ScoringCodecSourceBindingError(
                "Admission feature vector does not resolve exactly once in the live source."
            )
        vector = vectors[0]
    return candidates[0], results[0], vector


def _admission_from_json(
    value: Any,
    *,
    source_snapshot: ScoringSourceSnapshotV2,
) -> PreScoreAdmissionEvidenceV2:
    data = _object(value, _ADMISSION_KEYS, "PreScoreAdmissionEvidenceV2")
    candidate_id = _text(data["candidate_id"], "candidate_id")
    result_id = _text(data["constraint_result_id"], "constraint_result_id")
    vector_id = _optional_text(
        data["feature_vector_candidate_id"], "feature_vector_candidate_id"
    )
    candidate, result, vector = _find_source_members(
        source_snapshot,
        candidate_id=candidate_id,
        constraint_result_id=result_id,
        feature_vector_candidate_id=vector_id,
    )
    admission = PreScoreAdmissionEvidenceV2(
        admission_id=_text(data["admission_id"], "admission_id"),
        source_snapshot_id=_text(data["source_snapshot_id"], "source_snapshot_id"),
        candidate=candidate,
        constraint_result=result,
        feature_vector=vector,
        state=_enum(data["state"], AdmissionStateV2, "state"),
        policy_id=_optional_text(data["policy_id"], "policy_id"),
        policy_version=_optional_text(data["policy_version"], "policy_version"),
        evidence_references=tuple(
            _text(item, "evidence_references item")
            for item in _array(data["evidence_references"], "evidence_references")
        ),
        component_id=_text(data["component_id"], "component_id"),
        component_version=_text(data["component_version"], "component_version"),
        record_version=_text(data["record_version"], "record_version"),
    )
    if admission.source_snapshot_id != source_snapshot.source_snapshot_id:
        raise ScoringCodecSourceBindingError(
            "Admission source_snapshot_id differs from the exact live source."
        )
    if admission.admission_id != expected_admission_id(admission):
        _fail("PreScoreAdmissionEvidenceV2 deterministic ID mismatch.")
    return admission


def _score(entry: CandidateScoreEvidenceV2) -> dict[str, Any]:
    entry.__post_init__()
    binding = entry.trusted_scorer_binding
    if entry.raw_score is None:
        raw_score = None
    elif binding is None:
        _fail("An available raw score requires its exact trusted binding.")
    else:
        raw_score = canonical_decimal_string(
            entry.raw_score,
            precision=binding.numeric_precision,
            scale=binding.numeric_scale,
        )
    return {
        "admission": _admission(entry.admission),
        "component_id": entry.component_id,
        "component_version": entry.component_version,
        "not_applicable_reason": (
            None
            if entry.not_applicable_reason is None
            else entry.not_applicable_reason.value
        ),
        "raw_score": raw_score,
        "record_version": entry.record_version,
        "score_evidence_id": entry.score_evidence_id,
        "score_status": entry.score_status.value,
        "trusted_scorer_binding": (
            None if binding is None else _binding(binding)
        ),
    }


_SCORE_KEYS = (
    "admission", "component_id", "component_version", "not_applicable_reason",
    "raw_score", "record_version", "score_evidence_id", "score_status",
    "trusted_scorer_binding",
)


def expected_score_evidence_id(entry: CandidateScoreEvidenceV2) -> str:
    return deterministic_content_id(
        "pantryproof.candidate-score-evidence.v2",
        _score(entry),
        id_field="score_evidence_id",
    )


def _score_from_json(
    value: Any,
    *,
    source_snapshot: ScoringSourceSnapshotV2,
    exact_binding: TrustedScorerBindingV1 | None,
) -> CandidateScoreEvidenceV2:
    data = _object(value, _SCORE_KEYS, "CandidateScoreEvidenceV2")
    admission = _admission_from_json(data["admission"], source_snapshot=source_snapshot)
    encoded_binding = data["trusted_scorer_binding"]
    if encoded_binding is None:
        binding = None
    elif exact_binding is None:
        if encoded_binding is not None:
            raise ScoringCodecSourceBindingError(
                "Candidate binding is present without the aggregate exact binding."
            )
        binding = None  # pragma: no cover - the branch above always raises
    else:
        if encoded_binding != _binding(exact_binding):
            raise ScoringCodecSourceBindingError(
                "Candidate binding differs from the aggregate exact binding."
            )
        binding = exact_binding
    status = _enum(data["score_status"], ScoreStatusV2, "score_status")
    if data["raw_score"] is None:
        raw_score = None
    else:
        if binding is None:
            _fail("Serialized raw_score requires trusted_scorer_binding.")
        raw_score = parse_canonical_decimal(
            data["raw_score"],
            precision=binding.numeric_precision,
            scale=binding.numeric_scale,
        )
    entry = CandidateScoreEvidenceV2(
        score_evidence_id=_text(data["score_evidence_id"], "score_evidence_id"),
        admission=admission,
        score_status=status,
        raw_score=raw_score,
        not_applicable_reason=(
            None
            if data["not_applicable_reason"] is None
            else _enum(
                data["not_applicable_reason"],
                ScoreNotApplicableReasonV2,
                "not_applicable_reason",
            )
        ),
        trusted_scorer_binding=binding,
        component_id=_text(data["component_id"], "component_id"),
        component_version=_text(data["component_version"], "component_version"),
        record_version=_text(data["record_version"], "record_version"),
    )
    if entry.score_evidence_id != expected_score_evidence_id(entry):
        _fail("CandidateScoreEvidenceV2 deterministic ID mismatch.")
    return entry


def _audit(audit: FieldScoringAuditV2) -> dict[str, Any]:
    audit.__post_init__()
    return {
        "admitted_candidate_count": audit.admitted_candidate_count,
        "admitted_candidate_ids": list(audit.admitted_candidate_ids),
        "candidate_scores": [_score(entry) for entry in audit.candidate_scores],
        "completion_state": audit.completion_state.value,
        "component_id": audit.component_id,
        "component_version": audit.component_version,
        "field_audit_id": audit.field_audit_id,
        "record_version": audit.record_version,
        "resolver_invocation": audit.resolver_invocation.value,
        "resolver_result": (
            None if audit.resolver_result is None else _resolver(audit.resolver_result)
        ),
        "source_snapshot": _source_snapshot(audit.source_snapshot),
        "trusted_scorer_binding": (
            None
            if audit.trusted_scorer_binding is None
            else _binding(audit.trusted_scorer_binding)
        ),
    }


_AUDIT_KEYS = (
    "admitted_candidate_count", "admitted_candidate_ids", "candidate_scores",
    "completion_state", "component_id", "component_version", "field_audit_id",
    "record_version", "resolver_invocation", "resolver_result",
    "source_snapshot", "trusted_scorer_binding",
)


def expected_field_audit_id(audit: FieldScoringAuditV2) -> str:
    return deterministic_content_id(
        "pantryproof.field-scoring-audit.v2",
        _audit(audit),
        id_field="field_audit_id",
    )


def _require_exact_source_snapshot(
    value: Any,
    exact_source_snapshot: ScoringSourceSnapshotV2,
) -> None:
    if value != _source_snapshot(exact_source_snapshot):
        raise ScoringCodecSourceBindingError(
            "Serialized source snapshot differs from the exact live scoring source."
        )
    if exact_source_snapshot.source_snapshot_id != expected_source_snapshot_id(
        exact_source_snapshot
    ):
        _fail("ScoringSourceSnapshotV2 deterministic ID mismatch.")


def _audit_from_json(
    value: Any,
    *,
    source_snapshot: ScoringSourceSnapshotV2,
) -> FieldScoringAuditV2:
    data = _object(value, _AUDIT_KEYS, "FieldScoringAuditV2")
    _require_exact_source_snapshot(data["source_snapshot"], source_snapshot)
    binding = (
        None
        if data["trusted_scorer_binding"] is None
        else _binding_from_json(data["trusted_scorer_binding"])
    )
    resolver = (
        None
        if data["resolver_result"] is None
        else _resolver_from_json(data["resolver_result"], exact_binding=binding)
    )
    entries = tuple(
        _score_from_json(
            item,
            source_snapshot=source_snapshot,
            exact_binding=binding,
        )
        for item in _array(data["candidate_scores"], "candidate_scores")
    )
    audit = FieldScoringAuditV2(
        field_audit_id=_text(data["field_audit_id"], "field_audit_id"),
        source_snapshot=source_snapshot,
        candidate_scores=entries,
        admitted_candidate_ids=tuple(
            _text(item, "admitted_candidate_ids item")
            for item in _array(
                data["admitted_candidate_ids"], "admitted_candidate_ids"
            )
        ),
        admitted_candidate_count=_integer(
            data["admitted_candidate_count"], "admitted_candidate_count"
        ),
        resolver_invocation=_enum(
            data["resolver_invocation"],
            ScorerInvocationStateV2,
            "resolver_invocation",
        ),
        resolver_result=resolver,
        trusted_scorer_binding=binding,
        completion_state=_enum(
            data["completion_state"],
            FieldScoringCompletionStateV2,
            "completion_state",
        ),
        component_id=_text(data["component_id"], "component_id"),
        component_version=_text(data["component_version"], "component_version"),
        record_version=_text(data["record_version"], "record_version"),
    )
    if audit.field_audit_id != expected_field_audit_id(audit):
        _fail("FieldScoringAuditV2 deterministic ID mismatch.")
    return audit


def _failure(failure: FieldScoringFailureV2) -> dict[str, Any]:
    failure.__post_init__()
    return {
        "admissions": [_admission(item) for item in failure.admissions],
        "admitted_candidate_ids": list(failure.admitted_candidate_ids),
        "component_id": failure.component_id,
        "component_version": failure.component_version,
        "failure_code": failure.failure_code,
        "failure_id": failure.failure_id,
        "failure_state": failure.failure_state.value,
        "record_version": failure.record_version,
        "resolver_invocation": failure.resolver_invocation.value,
        "resolver_result": (
            None
            if failure.resolver_result is None
            else _resolver(failure.resolver_result)
        ),
        "source_snapshot": _source_snapshot(failure.source_snapshot),
    }


_FAILURE_KEYS = (
    "admissions", "admitted_candidate_ids", "component_id", "component_version",
    "failure_code", "failure_id", "failure_state", "record_version",
    "resolver_invocation", "resolver_result", "source_snapshot",
)


def expected_field_failure_id(failure: FieldScoringFailureV2) -> str:
    return deterministic_content_id(
        "pantryproof.field-scoring-failure.v2",
        _failure(failure),
        id_field="failure_id",
    )


def _failure_from_json(
    value: Any,
    *,
    source_snapshot: ScoringSourceSnapshotV2,
) -> FieldScoringFailureV2:
    data = _object(value, _FAILURE_KEYS, "FieldScoringFailureV2")
    _require_exact_source_snapshot(data["source_snapshot"], source_snapshot)
    admissions = tuple(
        _admission_from_json(item, source_snapshot=source_snapshot)
        for item in _array(data["admissions"], "admissions")
    )
    resolver = (
        None
        if data["resolver_result"] is None
        else _resolver_from_json(data["resolver_result"])
    )
    failure = FieldScoringFailureV2(
        failure_id=_text(data["failure_id"], "failure_id"),
        source_snapshot=source_snapshot,
        admissions=admissions,
        admitted_candidate_ids=tuple(
            _text(item, "admitted_candidate_ids item")
            for item in _array(
                data["admitted_candidate_ids"], "admitted_candidate_ids"
            )
        ),
        resolver_invocation=_enum(
            data["resolver_invocation"],
            ScorerInvocationStateV2,
            "resolver_invocation",
        ),
        resolver_result=resolver,
        failure_state=_enum(
            data["failure_state"], FieldScoringFailureStateV2, "failure_state"
        ),
        failure_code=_text(data["failure_code"], "failure_code"),
        component_id=_text(data["component_id"], "component_id"),
        component_version=_text(data["component_version"], "component_version"),
        record_version=_text(data["record_version"], "record_version"),
    )
    if failure.failure_id != expected_field_failure_id(failure):
        _fail("FieldScoringFailureV2 deterministic ID mismatch.")
    return failure


def _operation(result: ScoringOperationResultV2) -> dict[str, Any]:
    result.__post_init__()
    if isinstance(result.outcome, FieldScoringAuditV2):
        outcome_type = "FIELD_SCORING_AUDIT"
        outcome = _audit(result.outcome)
    elif isinstance(result.outcome, FieldScoringFailureV2):
        outcome_type = "FIELD_SCORING_FAILURE"
        outcome = _failure(result.outcome)
    else:  # pragma: no cover - guarded by the contract constructor
        _fail("Unsupported scoring operation outcome.")
    return {
        "operation_result_id": result.operation_result_id,
        "outcome": outcome,
        "outcome_type": outcome_type,
        "record_version": result.record_version,
    }


_OPERATION_KEYS = (
    "operation_result_id", "outcome", "outcome_type", "record_version",
)


def expected_operation_result_id(result: ScoringOperationResultV2) -> str:
    return deterministic_content_id(
        "pantryproof.scoring-operation-result.v2",
        _operation(result),
        id_field="operation_result_id",
    )


def _validate_deterministic_ids(result: ScoringOperationResultV2) -> None:
    outcome = result.outcome
    snapshot = outcome.source_snapshot
    if snapshot.source_snapshot_id != expected_source_snapshot_id(snapshot):
        _fail("ScoringSourceSnapshotV2 deterministic ID mismatch.")
    admissions = (
        tuple(entry.admission for entry in outcome.candidate_scores)
        if isinstance(outcome, FieldScoringAuditV2)
        else outcome.admissions
    )
    for admission in admissions:
        if admission.admission_id != expected_admission_id(admission):
            _fail("PreScoreAdmissionEvidenceV2 deterministic ID mismatch.")
    if isinstance(outcome, FieldScoringAuditV2):
        for entry in outcome.candidate_scores:
            if entry.score_evidence_id != expected_score_evidence_id(entry):
                _fail("CandidateScoreEvidenceV2 deterministic ID mismatch.")
        if outcome.field_audit_id != expected_field_audit_id(outcome):
            _fail("FieldScoringAuditV2 deterministic ID mismatch.")
    elif outcome.failure_id != expected_field_failure_id(outcome):
        _fail("FieldScoringFailureV2 deterministic ID mismatch.")
    if result.operation_result_id != expected_operation_result_id(result):
        _fail("ScoringOperationResultV2 deterministic ID mismatch.")


def scoring_operation_result_v2_to_json_bytes(
    result: ScoringOperationResultV2,
) -> bytes:
    """Serialize one complete operation after source and ID revalidation."""

    if not isinstance(result, ScoringOperationResultV2):
        _fail("result must be ScoringOperationResultV2.")
    result.__post_init__()
    _validate_deterministic_ids(result)
    envelope = {
        "record": _operation(result),
        "record_type": "ScoringOperationResultV2",
        "schema_id": SCORING_CODEC_SCHEMA_ID,
        "schema_version": SCORING_CODEC_SCHEMA_VERSION,
    }
    return canonical_json_bytes(envelope)


def scoring_operation_result_v2_from_json_bytes(
    payload: bytes,
    *,
    source_snapshot: ScoringSourceSnapshotV2,
) -> ScoringOperationResultV2:
    """Decode against the exact live source; JSON cannot recreate identity."""

    if not isinstance(source_snapshot, ScoringSourceSnapshotV2):
        _fail("source_snapshot must be ScoringSourceSnapshotV2.")
    source_snapshot.__post_init__()
    envelope = _object(
        parse_canonical_json_bytes(payload),
        ("record", "record_type", "schema_id", "schema_version"),
        "ScoringEnvelopeV2",
    )
    if envelope["schema_id"] != SCORING_CODEC_SCHEMA_ID:
        _fail("Unsupported scoring schema ID.")
    if envelope["schema_version"] != SCORING_CODEC_SCHEMA_VERSION:
        _fail("Unsupported scoring schema version.")
    if envelope["record_type"] != "ScoringOperationResultV2":
        _fail("Unsupported scoring record type.")
    data = _object(envelope["record"], _OPERATION_KEYS, "ScoringOperationResultV2")
    outcome_type = data["outcome_type"]
    if outcome_type == "FIELD_SCORING_AUDIT":
        outcome = _audit_from_json(data["outcome"], source_snapshot=source_snapshot)
    elif outcome_type == "FIELD_SCORING_FAILURE":
        outcome = _failure_from_json(data["outcome"], source_snapshot=source_snapshot)
    else:
        _fail("Unsupported scoring outcome type.")
    result = ScoringOperationResultV2(
        operation_result_id=_text(
            data["operation_result_id"], "operation_result_id"
        ),
        outcome=outcome,
        record_version=_text(data["record_version"], "record_version"),
    )
    _validate_deterministic_ids(result)
    return result


__all__ = (
    "SCORING_CODEC_SCHEMA_ID",
    "SCORING_CODEC_SCHEMA_VERSION",
    "SCORING_CODEC_VERSION",
    "ScoringCodecError",
    "ScoringCodecSourceBindingError",
    "canonical_decimal_string",
    "canonical_json_bytes",
    "deterministic_content_id",
    "expected_admission_id",
    "expected_field_audit_id",
    "expected_field_failure_id",
    "expected_operation_result_id",
    "expected_score_evidence_id",
    "expected_source_snapshot_id",
    "parse_canonical_decimal",
    "parse_canonical_json_bytes",
    "scoring_operation_result_v2_from_json_bytes",
    "scoring_operation_result_v2_to_json_bytes",
)


