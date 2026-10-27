# Offline Evaluation Manifest and Exclusion Ledger V0

Status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

## 1. Authority and verification limitation

This implementation follows `docs/proposed_evaluation_protocol_v0.md`, the
Task 2.5A reference contract, the thesis-traceability document, and the shared
runtime-contract boundaries. The moderated FYP1 thesis PDF was not available in
the repository or at the previously recorded external path during Task 2.5B.
Requirements attributed to the thesis below are therefore
`THESIS_REQUIRED` as traced by the supplied protocol; direct PDF verification
remains pending and is not claimed here.

The code is synthetic-only infrastructure. It does not establish a collected
dataset, lawful use, ethics approval, consent, cohort approval, a methodology
freeze, authenticated artifacts, held-out readiness, or an evaluation result.

## 2. Scope and relationship to Task 2.5A

The manifest stores dataset membership and receipt IDs. It deliberately does
not copy `TierAReferenceReceipt` fields, values, annotations, or source evidence.
The ledger may cross-check receipt, row, field, and availability claims against
independently supplied Task 2.5A records. It never receives prediction output as
reference truth and never changes a Task 2.5A record.

No runtime module imports these offline records. No OCR, extraction, correction,
alignment, fitting, split generation, metric computation, bootstrap, CIER,
calibration, PT1/PT2 selection, or held-out execution is implemented.

## 3. Requirement traceability

| Requirement | V0 representation | Classification |
|---|---|---|
| Separate grouped training, validation, and held-out identities | `PartitionRole` and `PartitionDefinition` | `THESIS_REQUIRED` |
| Alignment development is a training subset, not a fourth partition | `AlignmentDevelopmentSubset` plus manifest validation | `THESIS_REQUIRED` |
| Alignment receipts are excluded from fitting | `FittingExclusionEvidence`; declared evidence does not prove the fit manifest was checked | `THESIS_REQUIRED`; record shape is `PROPOSED_DEVELOPMENT_CHOICE` |
| Related transactions, duplicates, alternate captures, related records, and contributors cannot cross partitions | `RelatedGroupKind`, `RelatedRecordGroup`, and transitive connected-component validation | `THESIS_REQUIRED` |
| Primary, unseen-retailer, and branch analyses stay distinct | `CohortKind` and separate `CohortDefinition` identities | `THESIS_REQUIRED`; exact record shape is `PROPOSED_DEVELOPMENT_CHOICE` |
| A hash string is not authentication | `UNAVAILABLE`, `DECLARED_DIGEST`, and `VERIFIED_DIGEST` with mandatory verification evidence | `THESIS_REQUIRED` boundary from the protocol |
| Available truth plus missing prediction remains an error | Typed ledger category/reason/action mapping and Task 2.5A cross-check | `THESIS_REQUIRED` |
| Truth-dependent assertions require adjudicated field evidence | The target Task 2.5A field must reference a provenance adjudication event | `THESIS_REQUIRED`; field-local validation is a `PROPOSED_DEVELOPMENT_CHOICE` |
| Missing optional retailer price evidence cannot remove available unit-price truth | Separate optional-external-reference category and reason | `THESIS_REQUIRED` |
| Empty or invalid metric evidence is not fabricated as zero | `METRIC_NOT_ASSESSABLE` with `REPORT_NOT_ESTIMABLE` | `THESIS_REQUIRED` |
| Exact split algorithm, grouping policy, eligibility rule, and cohort thresholds are not selected | No generator or selection algorithm exists; policy references are nullable | `PENDING_APPROVAL` |

## 4. Public manifest records

All records are frozen, slotted dataclasses and all stored collections are
tuples.

- `DatasetTier`: V0 supports only `TIER_A`.
- `PartitionRole`: `TRAINING`, `VALIDATION`, and `HELD_OUT_TEST`.
- `CohortKind`: primary Tier A, unseen retailer, and branch generalization.
- `RelatedGroupKind`: transaction, exact duplicate, near duplicate, alternate
  capture, related record, and contributor.
- `FittingExclusionEvidenceState`: declared or independently verified.
- `DigestEvidenceState`: unavailable, declared digest, or verified digest.
- `AuditProvenance`: event, source, process version, and optional recorded time.
- `PartitionDefinition`: stable partition ID and role.
- `ReceiptManifestEntry`: de-identified Task 2.5A receipt ID, partition ID, and
  membership provenance reference.
- `RelatedRecordGroup`: typed group ID, declared receipt membership, and
  provenance reference.
- `CohortDefinition`: distinct cohort ID/kind, dataset link, declared receipt
  membership, and definition reference. It has no approval flag.
- `AlignmentDevelopmentSubset`: training receipt IDs and selection provenance.
- `FittingExclusionEvidence`: subset link, declared excluded IDs, fit-manifest
  reference, evidence state, and optional independent-verification reference.
- `DigestVerificationEvidence`: verifier, verification-record, and timestamp
  references supplied by an external process.
- `DigestEvidence`: typed digest evidence with state-dependent fields.
- `EvaluationManifest`: versioned dataset envelope containing the preceding
  records plus nullable grouping and eligibility policy references.

Public functions are:

- `validate_evaluation_manifest()` for structural and leakage validation;
- `related_receipt_components()` for canonical transitive group components;
- `serialize_evaluation_manifest()` for deterministic JSON.

`PROPOSED_DEVELOPMENT_CHOICE`: Public names, enum spellings, schema version
`"0"`, the shared identifier grammar, tuple storage, exact provenance fields,
and canonical JSON form are development interfaces rather than thesis names.

## 5. Manifest validation boundaries

### 5.1 Partition and membership integrity

V0 requires one distinct identity for each of the three Tier A partition roles.
A receipt appears once and references one known partition. Duplicate membership
and conflicting assignments are rejected.

The validator does not compute or check a 60/20/20 allocation, choose a seed,
balance strata, infer eligibility, or assign a receipt. Those are
`PENDING_APPROVAL` and require a separately frozen producer.

### 5.2 Declared grouping and transitive leakage

Every manifest receipt has exactly one declared transaction group and one
declared contributor group. Other relationship types are present only when
declared. The validator neither detects duplicates nor infers relationships.

All groups form one graph over known receipt IDs. Every connected component is
computed from the declared relationships, including overlaps between group
types. A component touching more than one partition is rejected. This catches
both direct and transitive leakage.

`PROPOSED_DEVELOPMENT_CHOICE`: Requiring exactly one transaction and contributor
group per manifest receipt is a completeness guard for this provisional schema.
The actual grouping policy, near-duplicate rule, related-transaction definition,
and contributor de-identification process remain `PENDING_APPROVAL`.

### 5.3 Alignment-development subset

The subset must contain known training receipts. It has no independent
partition role. A matching `FittingExclusionEvidence` record must cover every
subset receipt and may identify training receipts only.

A `DECLARED` fit-manifest reference is structurally sufficient for this V0
contract but is not proof that the referenced fit manifest exists, was opened,
or was checked. `INDEPENDENTLY_VERIFIED` additionally requires an external
verification reference. Neither state authorizes alignment execution.

### 5.4 Cohorts

One distinct identity is required for each of primary Tier A, unseen-retailer,
and branch-generalization analyses. The primary cohort contains every manifest
receipt. The other cohorts may be empty until achieved coverage is known.

No cohort record claims approval, minimum coverage, unseen-retailer eligibility,
or assessability. Those policies and results remain `PENDING_APPROVAL`.

### 5.5 Digests and freeze evidence

- `UNAVAILABLE` contains a reason and no digest data.
- `DECLARED_DIGEST` contains algorithm and value but no verification evidence.
- `VERIFIED_DIGEST` additionally requires a verifier reference, evidence
  reference, and verification timestamp supplied by an external process.

The schema never generates hashes, timestamps, verifier identities, approvals,
dataset IDs, or signatures. Structural construction of verified evidence does
not itself authenticate bytes or create freeze authority. The manifest exposes
no successful, ready, approved, or held-out-authorized state.

## 6. Public ledger records

- `LedgerStage`: dataset eligibility, reference annotation, prediction, system
  execution, review resolution, calibration, external reference, metric, or
  configuration/freeze.
- `ExclusionCategory`: the ten protocol categories for dataset exclusion,
  truth unavailability, adjudication pending, missing prediction, system
  failure, unresolved review, unavailable calibration/probability, unavailable
  optional reference, non-estimable metric, and configuration/freeze failure.
- `LedgerReasonCode`: finite V0 reason catalogue tied to categories.
- `DenominatorAction`: explicit permitted treatment; it is descriptive metadata
  and does not compute a denominator.
- `ExclusionLedgerEntry`: dataset/tier, optional partition/cohort/receipt/row/
  field, stage, category, reason, affected metrics, action, optional run/system/
  configuration/software references, and audit provenance.
- `ExclusionLedger`: versioned ledger/manifest/dataset envelope.

Public functions are `validate_exclusion_ledger()` and
`serialize_exclusion_ledger()`.

`PROPOSED_DEVELOPMENT_CHOICE`: Exact stage, category, reason, action, and field
spellings are the V0 executable taxonomy derived from protocol Section 8. They
remain provisional pending methodology approval.

## 7. Ledger invariants

Each category accepts only its declared stage, reason codes, and denominator
action. In particular:

- `DATASET_LEVEL_EXCLUSION` requires the stable receipt ID of the affected
  transaction; an anonymous or dataset-wide exclusion entry is invalid;
- `SYSTEM_MISSING_PREDICTION` requires `PREDICTION_ABSENT`, run/system context,
  and `INCLUDE_AS_EVALUATION_ERROR`;
- it cannot use dataset or truth-field exclusion actions;
- `REFERENCE_LABEL_UNAVAILABLE` can exclude only the affected truth-dependent
  field, must resolve to a Task 2.5A `UNAVAILABLE` field, and requires that
  field's adjudication-event reference to resolve within receipt provenance;
- `UNIT_PRICE_NOT_PRINTED_OR_DERIVABLE` is valid only for an actual
  `UNIT_PRICE` field; V0 adds no other field-specific annotation rules;
- `SYSTEM_MISSING_PREDICTION` likewise requires the affected available field
  to carry resolvable field-level adjudication evidence;
- optional retailer-price missingness uses
  `OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE` and
  `PRESERVE_OPTIONAL_MISSINGNESS`; it cannot be a truth-unavailability reason;
- `ADJUDICATION_PENDING` blocks affected evaluation and contradicts a finalized
  Task 2.5A receipt;
- system failure, unresolved review, and probability/calibration unavailability
  remain in applicable denominators under their frozen metric contracts;
- empty metric evidence is `REPORT_NOT_ESTIMABLE`, never numeric zero; and
- invalid configuration/freeze evidence blocks the affected run or metric.

These records do not decide TP, FP, FN, F1, CIER, coverage, calibration, or any
other score.

## 8. Cross-reference validation

When a manifest is supplied, ledger dataset, tier, partition, cohort, and
receipt memberships must agree, including for a legitimate ledger with no
entries. A `DATASET_LEVEL_EXCLUSION` cannot target a receipt already assigned
to the manifest: membership represents the manifest's eligible population for
this structural contract. Every such exclusion must identify its affected
receipt transaction. A prospectively dataset-excluded receipt may be absent
from manifest membership and must not claim a partition or cohort. The
validator never removes or reassigns membership.

When Task 2.5A references are supplied, receipt, row, and field links must agree.
Truth-dependent ledger categories require those independent references; a
reason string alone cannot establish availability. The affected field must
carry an adjudication-event ID that resolves in the Task 2.5A receipt
provenance. Available truth is required for a missing-prediction error, while
unavailable truth is required for a reference-label-unavailable entry. No
prediction object participates in this check.

`PROPOSED_DEVELOPMENT_CHOICE`: This cross-check is field-local. It does not
require every unrelated field to be finalized when the affected field has
independent adjudication evidence. This prevents one pending field from erasing
an auditable assertion about another field. A later evaluation runner must
still enforce the separate evaluation-level gate that only finalized,
eligible, frozen reference packages enter metric computation. This V0 ledger
does not implement or satisfy that gate.

## 9. Deterministic serialization and synthetic coverage

Both serializers validate first, retain nulls and enum values, sort object keys,
use compact separators, and canonically order identity-based collections.
Serialization is an interchange representation, not a database, signature, or
freeze artifact.

Synthetic tests cover valid/invalid identities, duplicate and conflicting
membership, all partition/cohort identities, direct and transitive group
leakage, alignment membership outside training, missing fitting-exclusion
evidence, declared versus verified evidence, cohort contradictions, digest
state boundaries, missing predictions that cannot become exclusions, genuine
truth unavailability, external-price missingness, adjudication pending,
duplicate ledger IDs, inconsistent reference links, manifest conflicts, and
deterministic serialization. Corrective regressions additionally cover
dataset exclusions without receipt identity or contradicting manifest
membership, unadjudicated
truth-dependent assertions, field-local adjudication with an unrelated pending
field, empty-ledger envelope mismatches, and the unit-price-specific reason
being applied to another field. They imply no actual dataset, approval,
collection, verification, held-out access, or empirical result.

## 10. Unsupported and pending decisions

The following remain `PENDING_APPROVAL` or unimplemented:

- corpus eligibility checklist and exclusion policy;
- exact grouped 60/20/20 split algorithm, seed, tie handling, and balance rules;
- transaction, near-duplicate, related-record, alternate-capture, and
  contributor grouping policies;
- unseen-retailer and branch-generalization eligibility and coverage rules;
- annotation guideline approval, independent double-annotation workflow, and
  actual adjudicator eligibility;
- normalization and unit-price derivation rules, arithmetic, rounding, and
  exception handling;
- fitting-manifest producer and independent fitting-exclusion audit;
- actual digest computation, byte authentication, registry, signatures,
  approvals, timestamps, and freeze authority;
- dataset collection, ethics/consent/access evidence, retention, and export;
- alignment selection, model fitting, configuration selection, runner access
  control, metric calculations, bootstrap, PT1/PT2, and held-out execution.

Structural validity is only a prerequisite for later independent review. It is
never a successful readiness or authorization decision.
