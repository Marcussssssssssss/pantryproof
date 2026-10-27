# Offline Receipt-Join Contract V0

Status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

Implementation authorization: synthetic-only receipt-join schema, structural
validation, synthetic alignment-readiness checks, deterministic serialization,
tests, documentation, and package exports.

This contract implements the six receipt-join design decisions recorded as
approved in `docs/evaluation_decision_log.md`. It does not authenticate a real
mapping, approve a dataset, implement row alignment, or authorize evaluation.
The supplied pre-implementation technical review was a ChatGPT conversation
review. It was not a separate human review, authenticated approval, signature,
or real-data identity-verification event.

## 1. Relationship to existing contracts

The join layer consumes, but does not modify:

- `TierAReferenceReceipt.receipt_id` and Task 2.5A reference finalization;
- `EvaluationManifest` membership, partition, cohort, dataset, and version
  identities from Task 2.5B;
- `PredictionBundle`, its complete `EvaluationRunScope`, and opaque
  `PredictionReceipt.runtime_receipt_id` values from Task 2.5C1A; and
- predictions produced by the B1/B2/B3 Task 2.5C1B adapters.

Runtime and reference identifiers remain independent namespaces. Equal text,
a filename, a source-token ID, a hash, or another shared-looking string is not
an association. An association exists only as an explicit `JOINED` entry and
still requires the approved evidence and trust checks before synthetic
alignment readiness can pass.

Reference fields and prediction values are not copied into a receipt join.

## 2. Decision traceability

| Decision | Executable V0 behavior |
| --- | --- |
| `SCH-JA-01` | `ReceiptJoinOutcome` has exactly `JOINED`, `REFERENCE_ONLY`, and `PREDICTION_ONLY`; structural validation requires complete, nonduplicated coverage of both applicable populations. |
| `SCH-JA-02` | `ReceiptJoinSet` stores a `prediction_bundle_id` and the complete immutable `EvaluationRunScope`; validation requires exact equality with one supplied `PredictionBundle`. |
| `SCH-JA-03` | `JOINED` requires `IDENTITY_ASSOCIATION` evidence. Both unmatched outcomes require `COVERAGE_ABSENCE` evidence and prohibit a fabricated absent-side identity. Evidence metadata remains separate from the synthetic trust registry. |
| `SCH-JA-04` | `validate_receipt_join_set()` and `validate_receipt_join_alignment_readiness()` are distinct. Structural validity never implies readiness or execution authorization. |
| `EVAL-JA-05` | Selected references are exactly manifest partition membership intersected with cohort membership. Prediction and selected-reference sides must each occur exactly once; joined links are one-to-one. Manifest identity/version are preserved. |
| `EVAL-JA-06` | Revisions are frozen records with explicit predecessor, amendment reason, amendment provenance, unique record/revision identities, acyclic single-successor lineage, immutable source scope, and one current head per complete scope. |

These decisions are design-approved only for synthetic implementation. This
implementation remains subject to independent technical review and explicit
acceptance.

## 3. Public schema API

All records are frozen, slotted dataclasses. All collections are tuples.
`RECEIPT_JOIN_SCHEMA_VERSION` is `"0"`.

### 3.1 Enums

- `ReceiptJoinOutcome`: `JOINED`, `REFERENCE_ONLY`, `PREDICTION_ONLY`.
- `ReceiptJoinEvidenceKind`: `IDENTITY_ASSOCIATION` or
  `COVERAGE_ABSENCE`.
- `ReceiptJoinVerificationState`: `UNVERIFIED`, `DECLARED`, or
  `INDEPENDENTLY_VERIFIED`.
- `ReceiptJoinAuthorizationState`: `UNAVAILABLE`, `DECLARED`, or
  `INDEPENDENTLY_VERIFIED`.
- `ReceiptJoinTrustBoundaryKind`: only `SYNTHETIC_FIXTURE` in V0.

### 3.2 Evidence, provenance, and authorization

- `ReceiptJoinProvenance` records an event ID, process version, one or more
  source references, an actor reference, optional recorded time, and schema
  version. These are audit pointers, not authentication.
- `ReceiptJoinVerificationEvidence` records a verification event, verifier
  reference, verification-record reference, optional time, and schema version.
  Populating it is a structural claim only.
- `ReceiptJoinEvidence` records the claim kind, declared verification state,
  evidence references, optional verification metadata, and an unavailable
  reason where appropriate.
- `ReceiptJoinAuthorization` records the declared authorization state,
  authority and authorization-record references, optional verification
  metadata, and an unavailable reason where appropriate.

`UNVERIFIED` evidence and `UNAVAILABLE` authorization cannot carry declared or
verified data. Declared states require their identifying references and cannot
carry independent-verification metadata. Independently verified states require
both the ordinary references and a typed verification record.

These constructor rules prevent contradictory representations. They do not
confirm that an actor or verifier is eligible, that a record is authentic, or
that an external event occurred.

### 3.3 Join entries

`ReceiptJoinEntry` fields are:

- `join_entry_id`;
- `outcome`;
- nullable `runtime_receipt_id`;
- nullable `reference_receipt_id`;
- outcome-specific `evidence`;
- `provenance`;
- nullable `unmatched_reason`; and
- `schema_version`.

Required shapes are:

| Outcome | Runtime ID | Reference ID | Evidence kind | Unmatched reason |
| --- | --- | --- | --- | --- |
| `JOINED` | required | required | `IDENTITY_ASSOCIATION` | prohibited |
| `REFERENCE_ONLY` | prohibited | required | `COVERAGE_ABSENCE` | required |
| `PREDICTION_ONLY` | required | prohibited | `COVERAGE_ABSENCE` | required |

`REFERENCE_ONLY` states that the selected reference receipt has no associated
prediction receipt in the supplied complete prediction scope. It does not
itself calculate a false negative, classify a system failure, or decide metric
denominators. `PREDICTION_ONLY` likewise records coverage, not a fabricated
reference identity or an exclusion decision.

### 3.4 Join sets and revisions

`ReceiptJoinSet` fields are:

- `join_set_id`, `join_set_version`, and globally collection-unique
  `revision_id`;
- `manifest_id`, `manifest_version`, and `dataset_version`;
- `prediction_bundle_id` and the complete `prediction_scope`;
- terminal `entries`;
- set-level `authorization` and `provenance`;
- optional `predecessor_revision_id`, `amendment_reason`, and
  `amendment_provenance`; and
- `schema_version`.

An initial revision has no predecessor or amendment fields. A successor must
identify its predecessor and carry an amendment reason, amendment provenance,
and at least declared authorization. Frozen dataclasses prevent ordinary field
assignment, but Python reflection can bypass that protection. Every public
validator therefore reconstructs the constructor-invariant checks over the
complete supplied join graph before applying cross-record validation.
Collection validation additionally prevents identity reuse, broken lineage,
cycles, forks, cross-scope predecessor substitution, and conflicting current
heads. Complete historical revisions remain serialized separately.

V0 cannot prove that an omitted older artifact was never rewritten outside
the supplied collection. External immutable storage or signatures remain a
future governance concern.

### 3.5 Synthetic trust context

`ReceiptJoinTrustContext` is explicit trust data supplied separately from the
join set being checked. It contains immutable, claim-bound records rather than
event-ID category lists:

- `ReceiptJoinTrustedEntryClaim` binds one verification event to the exact
  manifest and dataset versions, prediction bundle and complete evaluation
  scope, join-set identity/version/revision, join-entry identity, outcome,
  runtime/reference identities, evidence-reference set, and complete typed
  `ReceiptJoinVerificationEvidence`. This represents either the exact joined
  association or the exact present-side coverage/absence claim for an
  unmatched outcome.
- `ReceiptJoinTrustedAuthorizationClaim` binds one authorization-verification
  event to the same exact source scope and join-set revision, plus the exact
  authority, authorization-record reference, and typed verification metadata.

Claim IDs and verification-event IDs must be unique across one context. One
event therefore cannot support multiple unrelated claims. Readiness resolves
the event named by the join record and requires every bound attribute to match;
category or event membership alone is insufficient. Swapping receipt
identities, changing systems or bundles, changing a revision, changing an
outcome, or substituting evidence references invalidates the claim.

The only V0 boundary kind is `SYNTHETIC_FIXTURE`. A successful readiness check
means only that a synthetic fixture is internally consistent with separately
supplied synthetic trust claims. It must never be represented as real identity
authentication or evaluation authorization. Production validators do not
construct trusted claims from the join record they are checking.

The trust-context decomposition and exact claim records are
`PROPOSED_DEVELOPMENT_CHOICE`: they are the minimal V0 mechanism used to
execute approved `SCH-JA-03` and `SCH-JA-04` without claiming an external
authentication system.

## 4. Validation API and boundaries

### `validate_receipt_join_set()`

Inputs are one join set plus the exact `EvaluationManifest`,
`PredictionBundle`, and tuple of independent `TierAReferenceReceipt` records.
It validates:

- constructor invariants for the join set and every nested entry, evidence,
  verification, authorization, provenance, amendment-provenance, and scope
  record, even when an instance was reconstructed or modified after its
  original constructor call;
- supported source-contract structure;
- manifest ID/version, dataset ID/version/tier, partition, and cohort;
- exact prediction bundle ID and complete scope equality;
- resolution of every supplied runtime identity in that bundle;
- selected reference population as the intersection of partition and cohort;
- resolution of every selected reference identity in the supplied reference
  collection;
- unique join-entry IDs;
- outcome/evidence consistency;
- one occurrence of each prediction receipt;
- one occurrence of each selected reference receipt; and
- one-to-one joined cardinality.

It accepts structurally consistent unverified or declared evidence for audit.
It does not infer joins, authenticate evidence, require all unrelated reference
records to be finalized, or authorize alignment/evaluation.

### `validate_receipt_join_alignment_readiness()`

This calls structural validation first, then requires:

- finalized Task 2.5A records for the selected reference population;
- independently verified authorization metadata;
- independently verified outcome-specific evidence on every entry; and
- one exact external trusted claim for each verification event, bound to the
  intended identities, evidence, source scope, join-set revision, and
  authorization record.

The trust context, every trusted claim, their nested evaluation scopes, and
their provenance are also rechecked against their constructor invariants on
every readiness call. Post-construction mutation therefore fails closed rather
than relying on frozen-dataclass construction having occurred once.

The function raises `ReceiptJoinReadinessError` on failure. Passing means
synthetic alignment-input readiness only. It is not a held-out-ready status,
dataset eligibility decision, methodology freeze, or permission to run an
alignment algorithm.

### `validate_receipt_join_collection()`

This validates each revision against its manifest, prediction bundle, and
reference collection, then validates append-only lineage. It rejects:

- duplicate revision IDs;
- duplicate `(join_set_id, join_set_version)` record keys;
- missing manifests or bundles;
- broken predecessor references;
- predecessor links across join-set identities or immutable source scopes;
- cycles;
- multiple successors of one predecessor; and
- unrelated current heads for the same complete source scope.

The complete source scope includes the manifest and dataset versions,
partition, cohort, prediction bundle, run, system, configuration, and output
stage. Reusing a runtime receipt string in another complete scope is not a
collision.

### Errors

- `ReceiptJoinValidationError` reports structural, population, scope, and
  lineage errors.
- `ReceiptJoinReadinessError` is its readiness-specific subclass.
- Dataclass constructors raise `TypeError` or `ValueError` for malformed local
  combinations before cross-record validation.
- Public validators translate invalid consumed receipt-join graphs into the
  receipt-join validation error hierarchy consistently, including objects
  whose frozen fields were modified through reflective operations.

## 5. Deterministic serialization

- `serialize_receipt_join_set()` validates one revision against the supplied
  source contracts and emits canonical compact JSON.
- `serialize_receipt_join_collection()` validates complete lineage and emits
  every historical revision as a separate canonical JSON object.

Object keys are sorted. Join entries are ordered by outcome, null-safe
reference ID, null-safe runtime ID, and entry ID. Join-set collections are
ordered by their complete source identity followed by join-set and revision
identity. Evidence and provenance reference tuples are canonically sorted
because V0 treats them as identity sets rather than source-order sequences.
Nulls are preserved. Serialization does not create receipt identities,
entries, evidence, predictions, or reference values.

Canonical ordering is an interchange rule only. It is not receipt source
order, prediction output order, or a row-matcher processing rule.

## 6. Synthetic test coverage

The tests use generated identifiers and in-memory records only. They cover:

- all three terminal outcomes and complete two-sided coverage;
- differing runtime/reference IDs and equal text without trusted evidence;
- selected population as the partition/cohort intersection;
- fallback predictions, structured predictions with no item rows, and a
  missing prediction receipt;
- duplicate, missing, unknown, and substituted identities;
- one-to-one cardinality and manifest/bundle scope conflicts;
- evidence-kind and absent-side constructor failures;
- structurally valid but not ready records;
- swapped receipt associations and reused trust events across unrelated
  claims, systems, bundles, and revisions;
- exact claim-bound trust failures and successful synthetic readiness;
- post-construction mutations of schema versions, required reasons, enums,
  nested verification/authorization metadata, and trusted claims;
- a draft selected reference that passes structural validation but fails
  readiness;
- deterministic canonical JSON from equivalently reconstructed record graphs;
- frozen records;
- valid append-only history, broken lineage, cycles, forks, and undocumented
  or unauthorized amendment attempts.

The tests do not assert receipt identity correctness, dataset eligibility,
annotation agreement, extraction accuracy, metric outcomes, or real
verification.

## 7. Requirements, approved decisions, and development choices

The proposed evaluation protocol traces thesis requirements for independent
reference truth, separation of runtime and evaluation state, leakage-controlled
population handling, explicit treatment of missing predictions, and frozen,
auditable evaluation inputs. This implementation relies on those
`THESIS_TRACED_REQUIREMENT` boundaries; it does not claim that its Python
record decomposition or exact state names appear verbatim in the thesis.

The six items in Section 2 are `APPROVED_EVALUATION_SCHEMA_DECISION` records in
the canonical evaluation decision log. They operationalize the relevant
thesis-traced boundaries for synthetic receipt joining, but are not relabelled
as direct thesis text.

The exact Python class names, field decomposition, compact JSON ordering,
exception hierarchy, claim-bound synthetic trust records, and consumption-time
constructor replay are `PROPOSED_DEVELOPMENT_CHOICE` implementations within
those approved decisions.

The following remain `PENDING_APPROVAL` or require a later authorization:

- real receipt identity-mapping procedure and evidence format;
- eligible creator, verifier, and authorizer roles, including any required
  separation of duties;
- authentication, signatures, immutable storage, and external trust service;
- dataset eligibility, ethics, consent, licensing, and access;
- actual manifest, dataset, prediction, join, configuration, and software
  freeze authority;
- row-alignment schema and blocked/completed row-alignment states;
- Unicode normalization, significant punctuation, source-order semantics,
  edit distance, tie breaking, and threshold selection;
- proposed-method adapters;
- metric and exclusion-ledger consequences of unmatched receipts;
- validation or held-out execution; and
- independent technical acceptance of this implementation.

No row-alignment link, matcher, normalization, Levenshtein calculation,
threshold fitting, metric calculation, evaluation runner, real data access, or
runtime/Leng-owned contract change is implemented here.
