"""Structural, lineage, and synthetic-readiness validation for receipt joins."""

from __future__ import annotations

from evaluation.manifest_schema import EvaluationManifest
from evaluation.manifest_validation import validate_evaluation_manifest
from evaluation.prediction_schema import EvaluationRunScope, PredictionBundle
from evaluation.prediction_validation import validate_prediction_bundle
from evaluation.receipt_join_schema import (
    ReceiptJoinAuthorization,
    ReceiptJoinAuthorizationState,
    ReceiptJoinEntry,
    ReceiptJoinEvidence,
    ReceiptJoinEvidenceKind,
    ReceiptJoinOutcome,
    ReceiptJoinProvenance,
    ReceiptJoinSet,
    ReceiptJoinTrustBoundaryKind,
    ReceiptJoinTrustContext,
    ReceiptJoinTrustedAuthorizationClaim,
    ReceiptJoinTrustedEntryClaim,
    ReceiptJoinVerificationEvidence,
    ReceiptJoinVerificationState,
)
from evaluation.reference_schema import TierAReferenceReceipt
from evaluation.reference_validation import (
    validate_evaluation_ready_receipt,
    validate_reference_collection,
)


class ReceiptJoinValidationError(ValueError):
    """Raised when receipt-join structure, coverage, or lineage is invalid."""


class ReceiptJoinReadinessError(ReceiptJoinValidationError):
    """Raised when a structurally valid join lacks synthetic trust evidence."""


def _fail(message: str) -> None:
    raise ReceiptJoinValidationError(message)


def _readiness_fail(message: str) -> None:
    raise ReceiptJoinReadinessError(message)


def _revalidate_record(
    value: object,
    expected: type,
    label: str,
    *,
    readiness: bool = False,
) -> None:
    fail = _readiness_fail if readiness else _fail
    if not isinstance(value, expected):
        fail(f"{label} has invalid record type {type(value).__name__}.")
    try:
        expected.__post_init__(value)
    except (AttributeError, TypeError, ValueError) as error:
        fail(f"{label} violates constructor invariants: {error}")


def _revalidate_join_set_graph(join_set: object) -> ReceiptJoinSet:
    _revalidate_record(join_set, ReceiptJoinSet, "join set")
    assert isinstance(join_set, ReceiptJoinSet)
    _revalidate_record(
        join_set.prediction_scope, EvaluationRunScope, "join-set prediction scope"
    )
    _revalidate_record(join_set.provenance, ReceiptJoinProvenance, "join provenance")
    _revalidate_record(
        join_set.authorization, ReceiptJoinAuthorization, "join authorization"
    )
    authorization = join_set.authorization
    if authorization.verification is not None:
        _revalidate_record(
            authorization.verification,
            ReceiptJoinVerificationEvidence,
            "authorization verification",
        )
    if join_set.amendment_provenance is not None:
        _revalidate_record(
            join_set.amendment_provenance,
            ReceiptJoinProvenance,
            "amendment provenance",
        )
    for index, entry in enumerate(join_set.entries):
        entry_label = f"join entry at index {index}"
        _revalidate_record(entry, ReceiptJoinEntry, entry_label)
        _revalidate_record(
            entry.provenance,
            ReceiptJoinProvenance,
            f"{entry_label} provenance",
        )
        _revalidate_record(
            entry.evidence, ReceiptJoinEvidence, f"{entry_label} evidence"
        )
        if entry.evidence.verification is not None:
            _revalidate_record(
                entry.evidence.verification,
                ReceiptJoinVerificationEvidence,
                f"{entry_label} verification",
            )
    return join_set


def _revalidate_trust_context_graph(trust_context: object) -> ReceiptJoinTrustContext:
    _revalidate_record(
        trust_context,
        ReceiptJoinTrustContext,
        "synthetic trust context",
        readiness=True,
    )
    assert isinstance(trust_context, ReceiptJoinTrustContext)
    _revalidate_record(
        trust_context.provenance,
        ReceiptJoinProvenance,
        "synthetic trust-context provenance",
        readiness=True,
    )
    for index, claim in enumerate(trust_context.entry_claims):
        label = f"trusted entry claim at index {index}"
        _revalidate_record(
            claim, ReceiptJoinTrustedEntryClaim, label, readiness=True
        )
        _revalidate_record(
            claim.prediction_scope,
            EvaluationRunScope,
            f"{label} prediction scope",
            readiness=True,
        )
        _revalidate_record(
            claim.verification,
            ReceiptJoinVerificationEvidence,
            f"{label} verification",
            readiness=True,
        )
    for index, claim in enumerate(trust_context.authorization_claims):
        label = f"trusted authorization claim at index {index}"
        _revalidate_record(
            claim,
            ReceiptJoinTrustedAuthorizationClaim,
            label,
            readiness=True,
        )
        _revalidate_record(
            claim.prediction_scope,
            EvaluationRunScope,
            f"{label} prediction scope",
            readiness=True,
        )
        _revalidate_record(
            claim.verification,
            ReceiptJoinVerificationEvidence,
            f"{label} verification",
            readiness=True,
        )
    return trust_context


def _selected_reference_ids(
    manifest: EvaluationManifest,
    *,
    partition_id: str,
    cohort_id: str,
) -> set[str]:
    partition_ids = {item.partition_id for item in manifest.partitions}
    if partition_id not in partition_ids:
        _fail("Join scope references an unknown manifest partition.")
    cohorts = {item.cohort_id: item for item in manifest.cohorts}
    cohort = cohorts.get(cohort_id)
    if cohort is None:
        _fail("Join scope references an unknown manifest cohort.")
    partition_members = {
        item.receipt_id
        for item in manifest.receipts
        if item.partition_id == partition_id
    }
    return partition_members & set(cohort.receipt_ids)


def _source_scope_key(join_set: ReceiptJoinSet) -> tuple[str, ...]:
    return (
        join_set.manifest_id,
        join_set.manifest_version,
        join_set.prediction_scope.dataset_id,
        join_set.dataset_version,
        join_set.prediction_scope.dataset_tier.value,
        join_set.prediction_scope.partition_id,
        join_set.prediction_scope.cohort_id,
        join_set.prediction_bundle_id,
        *join_set.prediction_scope.identity_key,
    )


def validate_receipt_join_set(
    join_set: ReceiptJoinSet,
    *,
    manifest: EvaluationManifest,
    prediction_bundle: PredictionBundle,
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> None:
    """Validate structure and complete coverage without granting readiness."""

    join_set = _revalidate_join_set_graph(join_set)
    if not isinstance(manifest, EvaluationManifest):
        raise TypeError("manifest must be an EvaluationManifest.")
    if not isinstance(prediction_bundle, PredictionBundle):
        raise TypeError("prediction_bundle must be a PredictionBundle.")
    if not isinstance(reference_receipts, tuple):
        raise TypeError("reference_receipts must be a tuple.")

    validate_evaluation_manifest(manifest)
    validate_prediction_bundle(prediction_bundle, manifest=manifest)
    validate_reference_collection(
        reference_receipts, require_evaluation_ready=False
    )

    if join_set.manifest_id != manifest.manifest_id:
        _fail("Join set references another manifest identity.")
    if join_set.manifest_version != manifest.manifest_version:
        _fail("Join set references another manifest version.")
    if join_set.dataset_version != manifest.dataset_version:
        _fail("Join set references another dataset version.")
    scope = join_set.prediction_scope
    if scope != prediction_bundle.scope:
        _fail("Join set must preserve the complete prediction-bundle scope.")
    if join_set.prediction_bundle_id != prediction_bundle.bundle_id:
        _fail("Join set references another prediction bundle.")
    if scope.dataset_id != manifest.dataset_id:
        _fail("Join scope and manifest dataset identities conflict.")
    if scope.dataset_tier is not manifest.dataset_tier:
        _fail("Join scope and manifest dataset tiers conflict.")

    selected_reference_ids = _selected_reference_ids(
        manifest,
        partition_id=scope.partition_id,
        cohort_id=scope.cohort_id,
    )
    reference_by_id = {item.receipt_id: item for item in reference_receipts}
    unresolved_selected = selected_reference_ids - set(reference_by_id)
    if unresolved_selected:
        _fail(
            "Selected manifest reference identities are absent from the supplied "
            f"reference collection: {sorted(unresolved_selected)}."
        )

    prediction_ids = {
        item.runtime_receipt_id for item in prediction_bundle.receipts
    }
    entry_ids: set[str] = set()
    covered_prediction_ids: set[str] = set()
    covered_reference_ids: set[str] = set()
    for entry in join_set.entries:
        if entry.join_entry_id in entry_ids:
            _fail(f"Duplicate join entry ID {entry.join_entry_id!r}.")
        entry_ids.add(entry.join_entry_id)

        if entry.outcome is ReceiptJoinOutcome.JOINED:
            if entry.evidence.kind is not ReceiptJoinEvidenceKind.IDENTITY_ASSOCIATION:
                _fail("JOINED entry has incompatible evidence kind.")
        else:
            if entry.evidence.kind is not ReceiptJoinEvidenceKind.COVERAGE_ABSENCE:
                _fail("Unmatched entry has incompatible evidence kind.")

        if entry.runtime_receipt_id is not None:
            if entry.runtime_receipt_id not in prediction_ids:
                _fail(
                    f"Join entry {entry.join_entry_id!r} references an unknown "
                    "runtime receipt identity."
                )
            if entry.runtime_receipt_id in covered_prediction_ids:
                _fail(
                    "A runtime receipt identity occurs more than once in the join set."
                )
            covered_prediction_ids.add(entry.runtime_receipt_id)

        if entry.reference_receipt_id is not None:
            if entry.reference_receipt_id not in selected_reference_ids:
                _fail(
                    f"Join entry {entry.join_entry_id!r} references a receipt outside "
                    "the manifest partition/cohort intersection."
                )
            if entry.reference_receipt_id in covered_reference_ids:
                _fail(
                    "A reference receipt identity occurs more than once in the join set."
                )
            covered_reference_ids.add(entry.reference_receipt_id)

    missing_predictions = prediction_ids - covered_prediction_ids
    extra_predictions = covered_prediction_ids - prediction_ids
    if missing_predictions or extra_predictions:
        _fail(
            "Join entries do not exactly cover the scoped prediction population; "
            f"missing={sorted(missing_predictions)}, extra={sorted(extra_predictions)}."
        )
    missing_references = selected_reference_ids - covered_reference_ids
    extra_references = covered_reference_ids - selected_reference_ids
    if missing_references or extra_references:
        _fail(
            "Join entries do not exactly cover the selected reference population; "
            f"missing={sorted(missing_references)}, extra={sorted(extra_references)}."
        )


def validate_receipt_join_alignment_readiness(
    join_set: ReceiptJoinSet,
    *,
    manifest: EvaluationManifest,
    prediction_bundle: PredictionBundle,
    reference_receipts: tuple[TierAReferenceReceipt, ...],
    trust_context: ReceiptJoinTrustContext,
) -> None:
    """Require synthetic trust registration after structural validation.

    Success means ready only for later synthetic row-alignment work.  It does
    not authenticate real evidence or authorize evaluation execution.
    """

    validate_receipt_join_set(
        join_set,
        manifest=manifest,
        prediction_bundle=prediction_bundle,
        reference_receipts=reference_receipts,
    )
    trust_context = _revalidate_trust_context_graph(trust_context)
    if (
        trust_context.boundary_kind
        is not ReceiptJoinTrustBoundaryKind.SYNTHETIC_FIXTURE
    ):
        _readiness_fail("V0 supports only the explicit synthetic-fixture boundary.")

    authorization = join_set.authorization
    if (
        authorization.state
        is not ReceiptJoinAuthorizationState.INDEPENDENTLY_VERIFIED
        or authorization.verification is None
    ):
        _readiness_fail("Join-set authorization is not independently verified.")
    authorization_event_id = authorization.verification.verification_event_id
    authorization_claims = {
        item.verification_event_id: item
        for item in trust_context.authorization_claims
    }
    authorization_claim = authorization_claims.get(authorization_event_id)
    if authorization_claim is None:
        _readiness_fail(
            "Authorization verification has no external trusted claim."
        )
    expected_authorization_binding = (
        join_set.manifest_id,
        join_set.manifest_version,
        join_set.dataset_version,
        join_set.prediction_bundle_id,
        join_set.prediction_scope,
        join_set.join_set_id,
        join_set.join_set_version,
        join_set.revision_id,
        authorization.authority_reference,
        authorization.authorization_record_reference,
        authorization.verification,
    )
    actual_authorization_binding = (
        authorization_claim.manifest_id,
        authorization_claim.manifest_version,
        authorization_claim.dataset_version,
        authorization_claim.prediction_bundle_id,
        authorization_claim.prediction_scope,
        authorization_claim.join_set_id,
        authorization_claim.join_set_version,
        authorization_claim.revision_id,
        authorization_claim.authority_reference,
        authorization_claim.authorization_record_reference,
        authorization_claim.verification,
    )
    if actual_authorization_binding != expected_authorization_binding:
        _readiness_fail(
            "Authorization trusted claim is bound to another scope or revision."
        )

    entry_claims = {
        item.verification_event_id: item for item in trust_context.entry_claims
    }
    for entry in join_set.entries:
        if (
            entry.evidence.state
            is not ReceiptJoinVerificationState.INDEPENDENTLY_VERIFIED
            or entry.evidence.verification is None
        ):
            _readiness_fail(
                f"Join entry {entry.join_entry_id!r} lacks verified evidence."
            )
        event_id = entry.evidence.verification.verification_event_id
        claim = entry_claims.get(event_id)
        if claim is None:
            _readiness_fail(
                f"Join entry {entry.join_entry_id!r} verification has no external "
                "trusted claim."
            )
        expected_binding = (
            join_set.manifest_id,
            join_set.manifest_version,
            join_set.dataset_version,
            join_set.prediction_bundle_id,
            join_set.prediction_scope,
            join_set.join_set_id,
            join_set.join_set_version,
            join_set.revision_id,
            entry.join_entry_id,
            entry.outcome,
            entry.runtime_receipt_id,
            entry.reference_receipt_id,
            tuple(sorted(entry.evidence.evidence_references)),
            entry.evidence.verification,
        )
        actual_binding = (
            claim.manifest_id,
            claim.manifest_version,
            claim.dataset_version,
            claim.prediction_bundle_id,
            claim.prediction_scope,
            claim.join_set_id,
            claim.join_set_version,
            claim.revision_id,
            claim.join_entry_id,
            claim.outcome,
            claim.runtime_receipt_id,
            claim.reference_receipt_id,
            tuple(sorted(claim.evidence_references)),
            claim.verification,
        )
        if actual_binding != expected_binding:
            _readiness_fail(
                f"Join entry {entry.join_entry_id!r} trusted claim is bound to "
                "another identity, outcome, scope, or revision."
            )

    selected_reference_ids = _selected_reference_ids(
        manifest,
        partition_id=join_set.prediction_scope.partition_id,
        cohort_id=join_set.prediction_scope.cohort_id,
    )
    for receipt in reference_receipts:
        if receipt.receipt_id in selected_reference_ids:
            try:
                validate_evaluation_ready_receipt(receipt)
            except ValueError as error:
                _readiness_fail(
                    f"Selected reference {receipt.receipt_id!r} is not finalized: "
                    f"{error}"
                )


def validate_receipt_join_collection(
    join_sets: tuple[ReceiptJoinSet, ...],
    *,
    manifests: tuple[EvaluationManifest, ...],
    prediction_bundles: tuple[PredictionBundle, ...],
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> None:
    """Validate join sets plus append-only, single-head revision lineage."""

    if not isinstance(join_sets, tuple):
        _fail("join_sets must be a tuple.")
    for value, name, expected in (
        (manifests, "manifests", EvaluationManifest),
        (prediction_bundles, "prediction_bundles", PredictionBundle),
        (reference_receipts, "reference_receipts", TierAReferenceReceipt),
    ):
        if not isinstance(value, tuple):
            raise TypeError(f"{name} must be a tuple.")
        if any(not isinstance(item, expected) for item in value):
            raise TypeError(f"{name} contains an invalid record.")

    manifests_by_key: dict[tuple[str, str], EvaluationManifest] = {}
    for manifest in manifests:
        key = (manifest.manifest_id, manifest.manifest_version)
        if key in manifests_by_key:
            _fail(f"Duplicate manifest identity/version {key!r}.")
        manifests_by_key[key] = manifest

    bundles_by_id: dict[str, PredictionBundle] = {}
    for bundle in prediction_bundles:
        if bundle.bundle_id in bundles_by_id:
            _fail(f"Duplicate prediction bundle ID {bundle.bundle_id!r}.")
        bundles_by_id[bundle.bundle_id] = bundle

    revisions: dict[str, ReceiptJoinSet] = {}
    record_keys: set[tuple[str, str]] = set()
    for join_set in join_sets:
        join_set = _revalidate_join_set_graph(join_set)
        if join_set.revision_id in revisions:
            _fail(f"Duplicate join-set revision ID {join_set.revision_id!r}.")
        revisions[join_set.revision_id] = join_set
        record_key = (join_set.join_set_id, join_set.join_set_version)
        if record_key in record_keys:
            _fail(f"Duplicate join-set record key {record_key!r}.")
        record_keys.add(record_key)

        manifest = manifests_by_key.get(
            (join_set.manifest_id, join_set.manifest_version)
        )
        if manifest is None:
            _fail("Join-set revision references an unavailable manifest revision.")
        bundle = bundles_by_id.get(join_set.prediction_bundle_id)
        if bundle is None:
            _fail("Join-set revision references an unavailable prediction bundle.")
        validate_receipt_join_set(
            join_set,
            manifest=manifest,
            prediction_bundle=bundle,
            reference_receipts=reference_receipts,
        )

    successor_counts: dict[str, int] = {revision_id: 0 for revision_id in revisions}
    for join_set in join_sets:
        predecessor_id = join_set.predecessor_revision_id
        if predecessor_id is None:
            continue
        predecessor = revisions.get(predecessor_id)
        if predecessor is None:
            _fail(
                f"Revision {join_set.revision_id!r} has a broken predecessor link."
            )
        if predecessor.join_set_id != join_set.join_set_id:
            _fail("A revision predecessor belongs to another join-set identity.")
        if _source_scope_key(predecessor) != _source_scope_key(join_set):
            _fail("A revision changes its immutable source scope.")
        successor_counts[predecessor_id] += 1
        if successor_counts[predecessor_id] > 1:
            _fail("A join-set revision has conflicting successor heads.")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(revision_id: str) -> None:
        if revision_id in visiting:
            _fail("Join-set revision lineage contains a cycle.")
        if revision_id in visited:
            return
        visiting.add(revision_id)
        predecessor_id = revisions[revision_id].predecessor_revision_id
        if predecessor_id is not None:
            visit(predecessor_id)
        visiting.remove(revision_id)
        visited.add(revision_id)

    for revision_id in revisions:
        visit(revision_id)

    heads_by_scope: dict[tuple[str, ...], list[str]] = {}
    for revision_id, join_set in revisions.items():
        if successor_counts[revision_id] == 0:
            heads_by_scope.setdefault(_source_scope_key(join_set), []).append(
                revision_id
            )
    for head_ids in heads_by_scope.values():
        if len(head_ids) > 1:
            _fail(
                "A complete source scope has conflicting current join-set heads: "
                f"{sorted(head_ids)}."
            )


__all__ = (
    "ReceiptJoinReadinessError",
    "ReceiptJoinValidationError",
    "validate_receipt_join_alignment_readiness",
    "validate_receipt_join_collection",
    "validate_receipt_join_set",
)
