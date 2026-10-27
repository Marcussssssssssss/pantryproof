"""Deterministic structural and leakage validation for offline manifests."""

from __future__ import annotations

from evaluation.manifest_schema import (
    CohortKind,
    EvaluationManifest,
    PartitionRole,
    RelatedGroupKind,
)


class ManifestValidationError(ValueError):
    """Raised when manifest structure or declared grouping is inconsistent."""


def _fail(message: str) -> None:
    raise ManifestValidationError(message)


def _require_unique(values: tuple[str, ...], name: str) -> None:
    if len(values) != len(set(values)):
        _fail(f"Duplicate {name}.")


def related_receipt_components(
    manifest: EvaluationManifest,
) -> tuple[tuple[str, ...], ...]:
    """Return canonical transitive components from declared group membership."""

    receipt_ids = tuple(entry.receipt_id for entry in manifest.receipts)
    parent = {receipt_id: receipt_id for receipt_id in receipt_ids}

    def find(receipt_id: str) -> str:
        while parent[receipt_id] != receipt_id:
            parent[receipt_id] = parent[parent[receipt_id]]
            receipt_id = parent[receipt_id]
        return receipt_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    known = set(receipt_ids)
    for group in manifest.related_groups:
        unknown = set(group.receipt_ids) - known
        if unknown:
            _fail(
                f"Group {group.group_id!r} references unknown receipts: "
                f"{sorted(unknown)}."
            )
        first = group.receipt_ids[0]
        for receipt_id in group.receipt_ids[1:]:
            union(first, receipt_id)

    components: dict[str, list[str]] = {}
    for receipt_id in receipt_ids:
        components.setdefault(find(receipt_id), []).append(receipt_id)
    return tuple(
        sorted((tuple(sorted(items)) for items in components.values()), key=lambda x: x)
    )


def _validate_partitions(manifest: EvaluationManifest) -> dict[str, PartitionRole]:
    partition_ids = tuple(item.partition_id for item in manifest.partitions)
    _require_unique(partition_ids, "partition ID")
    roles = tuple(item.role for item in manifest.partitions)
    if len(roles) != len(set(roles)):
        _fail("Each partition role must have one distinct partition identity.")
    if set(roles) != set(PartitionRole):
        _fail("Tier A requires training, validation, and held-out partition identities.")
    return {item.partition_id: item.role for item in manifest.partitions}


def _validate_receipts(
    manifest: EvaluationManifest,
    partitions: dict[str, PartitionRole],
) -> dict[str, str]:
    receipt_partitions: dict[str, str] = {}
    for entry in manifest.receipts:
        prior = receipt_partitions.get(entry.receipt_id)
        if prior is not None:
            if prior != entry.partition_id:
                _fail(
                    f"Receipt {entry.receipt_id!r} has conflicting partition assignments."
                )
            _fail(f"Duplicate receipt membership {entry.receipt_id!r}.")
        if entry.partition_id not in partitions:
            _fail(
                f"Receipt {entry.receipt_id!r} references an unknown partition."
            )
        receipt_partitions[entry.receipt_id] = entry.partition_id
    return receipt_partitions


def _validate_groups(
    manifest: EvaluationManifest,
    receipt_partitions: dict[str, str],
) -> None:
    group_ids = tuple(group.group_id for group in manifest.related_groups)
    _require_unique(group_ids, "related-record group ID")
    known = set(receipt_partitions)
    coverage = {
        kind: set()
        for kind in (RelatedGroupKind.TRANSACTION, RelatedGroupKind.CONTRIBUTOR)
    }
    for group in manifest.related_groups:
        unknown = set(group.receipt_ids) - known
        if unknown:
            _fail(
                f"Group {group.group_id!r} references unknown receipts: "
                f"{sorted(unknown)}."
            )
        if group.kind in coverage:
            overlap = coverage[group.kind] & set(group.receipt_ids)
            if overlap:
                _fail(
                    f"Receipts belong to multiple {group.kind.value} groups: "
                    f"{sorted(overlap)}."
                )
            coverage[group.kind].update(group.receipt_ids)
    for kind, members in coverage.items():
        missing = known - members
        if missing:
            _fail(
                f"Receipts lack declared {kind.value} grouping: {sorted(missing)}."
            )

    for component in related_receipt_components(manifest):
        component_partitions = {
            receipt_partitions[receipt_id] for receipt_id in component
        }
        if len(component_partitions) > 1:
            _fail(
                "A connected related-record component spans partitions: "
                f"{list(component)}."
            )


def _validate_cohorts(
    manifest: EvaluationManifest,
    receipt_partitions: dict[str, str],
) -> None:
    cohort_ids = tuple(cohort.cohort_id for cohort in manifest.cohorts)
    _require_unique(cohort_ids, "cohort ID")
    kinds = tuple(cohort.kind for cohort in manifest.cohorts)
    if len(kinds) != len(set(kinds)):
        _fail("Each cohort kind must have a separate, unique definition.")
    if set(kinds) != set(CohortKind):
        _fail(
            "Tier A requires separate primary, unseen-retailer, and "
            "branch-generalization cohort identities."
        )

    known = set(receipt_partitions)
    primary = None
    for cohort in manifest.cohorts:
        if cohort.dataset_id != manifest.dataset_id:
            _fail(f"Cohort {cohort.cohort_id!r} belongs to another dataset.")
        unknown = set(cohort.receipt_ids) - known
        if unknown:
            _fail(
                f"Cohort {cohort.cohort_id!r} references unknown receipts: "
                f"{sorted(unknown)}."
            )
        if cohort.kind is CohortKind.PRIMARY_TIER_A:
            primary = cohort
    if primary is None:
        _fail("Tier A requires one declared primary cohort identity.")
    if set(primary.receipt_ids) != known:
        _fail("The primary Tier A cohort must identify every manifest receipt.")


def _validate_alignment(
    manifest: EvaluationManifest,
    partitions: dict[str, PartitionRole],
    receipt_partitions: dict[str, str],
) -> None:
    subset = manifest.alignment_subset
    evidence = manifest.fitting_exclusion_evidence
    if subset is None:
        if evidence is not None:
            _fail("Fitting exclusion evidence has no alignment-development subset.")
        return
    if evidence is None:
        _fail("Alignment-development membership lacks fitting-exclusion evidence.")
    assert evidence is not None
    if evidence.subset_id != subset.subset_id:
        _fail("Fitting exclusion evidence refers to another alignment subset.")

    known = set(receipt_partitions)
    unknown = set(subset.receipt_ids) - known
    if unknown:
        _fail(f"Alignment subset references unknown receipts: {sorted(unknown)}.")
    for receipt_id in subset.receipt_ids:
        partition_id = receipt_partitions[receipt_id]
        if partitions[partition_id] is not PartitionRole.TRAINING:
            _fail("Alignment-development membership must be a subset of training.")
    evidence_unknown = set(evidence.excluded_receipt_ids) - known
    if evidence_unknown:
        _fail(
            "Fitting exclusion evidence references unknown receipts: "
            f"{sorted(evidence_unknown)}."
        )
    for receipt_id in evidence.excluded_receipt_ids:
        partition_id = receipt_partitions[receipt_id]
        if partitions[partition_id] is not PartitionRole.TRAINING:
            _fail("Fitting-exclusion evidence may identify training receipts only.")
    missing = set(subset.receipt_ids) - set(evidence.excluded_receipt_ids)
    if missing:
        _fail(
            "Fitting exclusion evidence does not cover alignment receipts: "
            f"{sorted(missing)}."
        )


def validate_evaluation_manifest(manifest: EvaluationManifest) -> None:
    """Validate declared structure and leakage, never held-out readiness."""

    if not isinstance(manifest, EvaluationManifest):
        raise TypeError("manifest must be an EvaluationManifest.")
    partitions = _validate_partitions(manifest)
    receipt_partitions = _validate_receipts(manifest, partitions)
    _validate_groups(manifest, receipt_partitions)
    _validate_cohorts(manifest, receipt_partitions)
    _validate_alignment(manifest, partitions, receipt_partitions)
    digest_ids = tuple(item.evidence_id for item in manifest.digest_evidence)
    _require_unique(digest_ids, "digest evidence ID")
