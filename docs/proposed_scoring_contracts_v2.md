# PantryProof structural scoring evidence V2

Status: jointly approved structural contract; synthetic-only implementation.

Research status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`.

This document describes the V2-native raw-scoring evidence boundary implemented
by `pipeline/proposed/scoring_contracts_v2.py` and
`pipeline/proposed/scoring_codec_v2.py`. It does not approve or implement a
scoring formula, trained scorer, model inference, calibration, probability,
candidate selection, replacement of permanent `c0`, controller behavior, or
persistence.

## 1. Upstream boundary

The scoring package consumes an already constructed
`FeatureConstructionResultV0`. That source retains:

- the exact `HardConstraintOperandAuditResultV0`;
- the complete c0-first D3 candidate population;
- exactly one unchanged `ConstraintResultV2` per retained candidate;
- feature vectors only for candidates whose V2 aggregate is `ELIGIBLE`; and
- the complete upstream `Theta_A` reference.

`ScoringSourceSnapshotV2` captures the exact feature-construction object once.
Repeated validation rejects substitution of that object. The source object
already protects the exact operand audit, candidate audits, V2 results,
eligible feature vectors, permanent c0 and source token observations.

The scoring snapshot additionally validates source component versions,
candidate and result uniqueness, c0-first ordering and one V2 result per D3
candidate. It does not alter any upstream record.

## 2. Record family

### 2.1 `ScoringSourceSnapshotV2`

This is the field-wide source anchor. It stores a snapshot ID, the exact live
feature-construction result and the ordered source component versions. Receipt,
field, `Theta_A`, c0, candidates, constraint results and eligible vectors are
derived from the source graph rather than copied from unverified caller text.

### 2.2 `PreScoreAdmissionEvidenceV2`

Admission is separate from V2 hard-constraint eligibility. The closed initial
states are:

- `ADMITTED`;
- `NOT_APPLICABLE_CONSTRAINT_REJECTED`;
- `NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE`; and
- `REJECTED_PRICE_ONLY_SUPPORT`.

Every admission carries the exact scoring-source snapshot ID. Both successful
and failed field aggregates reject admissions copied from another snapshot,
even when candidate and result identifiers happen to be value-equal.

`ADMITTED` and `REJECTED_PRICE_ONLY_SUPPORT` require an unchanged V2
`ELIGIBLE` result, its exact feature vector, a versioned policy identity and
nonempty structural evidence references. Constraint-rejected and
constraint-unavailable candidates receive the matching not-applicable state;
they have no feature vector and must not claim that the admission policy ran.

The price-only record is structural evidence only. Its policy ID, version and
evidence references do not authenticate an operational evaluator and do not
prove that one executed. No arbitrary Boolean is accepted as proof. A future
operational admission evaluator requires separate authorization and trust
binding.

### 2.3 `CandidateScoreEvidenceV2`

Exactly two score states exist initially:

- `AVAILABLE`: the candidate is `ADMITTED`, the raw score is a finite
  `Decimal`, and an exact `TrustedScorerBindingV1` is present;
- `NOT_APPLICABLE`: the score is null, the binding is null, and the typed
  reason follows exactly from the admission/V2 state.

The closed not-applicable reasons are:

- `CONSTRAINT_REJECTED`;
- `CONSTRAINT_UNAVAILABLE`; and
- `PRE_SCORE_REJECTED_PRICE_ONLY_SUPPORT`.

Candidate-local score `UNAVAILABLE` is not part of this version. Raw scores are
not probabilities and the record has no probability or selected-candidate
field.

### 2.4 `FieldScoringAuditV2`

A successful field audit contains:

- the exact source snapshot;
- exactly one candidate-score entry per retained D3 candidate, in exact D3
  order;
- the canonical admitted-candidate subsequence and count;
- resolver invocation state;
- the exact resolver result and scorer binding when scoring is structurally
  complete; and
- one of `COMPLETE_SCORED` or
  `COMPLETE_ZERO_ADMITTED_BYPASS`.

For `COMPLETE_SCORED`, every admitted candidate has an available score and all
such entries share the field audit's exact binding. The resolver is `READY`
and its parent `Theta_A`, manifest, feature schema and admission-policy
relationships must agree with the source graph.

### 2.5 `FieldScoringFailureV2`

Field-level failure is distinct from candidate score availability. The record
retains the complete source snapshot, one admission per candidate, canonical
admitted IDs, resolver invocation evidence where available, and a typed field
failure state. It contains no partial successful candidate-score aggregate.

Resolver `NOT_READY` and `NOT_VALID` map to distinct field failures.
Configuration, manifest, compatibility, integrity and unexpected execution
failures remain field-level. Invalid source evidence fails construction instead
of being relabelled as candidate unavailability.

### 2.6 `ScoringOperationResultV2`

This discriminated wrapper contains either one complete field audit or one
atomic field failure. It captures the exact outcome reference and does not
authorize any later selection, correction, review or persistence state.

## 3. Population and identity invariants

The source-bound constructors enforce all of the following:

1. Permanent c0 remains the first D3 candidate and remains self-bound.
2. Every retained D3 candidate appears exactly once.
3. Candidate order is unchanged.
4. Every candidate retains its exact V2 result object.
5. Every V2 result retains the exact permanent c0 object.
6. Eligible candidates retain their exact feature-vector objects.
7. Rejected and unavailable candidates have no feature vector.
8. Candidate, admission and score IDs are unique where required.
9. Receipt, field and complete `Theta_A` relationships remain unchanged.
10. Missing, additional, duplicate, reordered or value-equal substituted
    source objects are rejected.

These are live in-process identity guarantees. JSON cannot recreate Python
object identity. Public decoding therefore validates immutable content and
then binds the decoded evidence to an explicitly supplied, already validated
live `ScoringSourceSnapshotV2`.

## 4. Zero-admitted audit-only bypass

The bypass is valid only after complete source and population validation.

- Every retained candidate remains present.
- Every candidate score is `NOT_APPLICABLE`.
- `admitted_candidate_ids` is empty and the count is zero.
- Completion is `COMPLETE_ZERO_ADMITTED_BYPASS`.
- Resolver invocation is `NOT_INVOKED_ZERO_ADMITTED`.
- Resolver result and trusted binding are null.
- No readiness, raw score, probability, selection or replacement is inferred.

Malformed source evidence cannot use the bypass as a fallback. The bypass
contains no resolver or scorer call.

## 5. Decimal policy

The trusted scorer binding supplies numeric precision and scale. A raw score
must already be exactly representable under that policy:

- finite `Decimal` only;
- plain fixed-scale form;
- exactly the declared scale;
- no exponent notation on the wire;
- no leading plus sign or invalid leading zeros;
- no negative zero;
- no value exceeding declared precision; and
- no silent rounding or normalization.

The structural package does not freeze actual production precision, scale,
rounding mode, score range or scorer arithmetic.

## 6. Public codec

The codec uses a restricted RFC 8785/JCS-compatible JSON domain:

- UTF-8 bytes without a BOM;
- objects with printable ASCII keys sorted lexicographically;
- arrays retaining semantic order;
- strings, explicit null, Boolean and safe-range JSON integers;
- no JSON floating-point numbers or non-finite constants; and
- compact separators with deterministic escaping.

The decoder rejects malformed UTF-8, noncanonical bytes, duplicate keys,
unknown or missing keys, unsupported versions, invalid enum spellings,
incorrect nulls, noncanonical decimals and inconsistent source relationships.
All mappings are explicit; generic dataclass serialization is not used, so
private capture-once references cannot leak into the wire format.

Record IDs use SHA-256 over domain-separated canonical content with the
record's own ID field excluded from the preimage. These IDs are deterministic
content-integrity metadata. They are not signatures, owner approvals or source
authentication.

## 7. Synthetic fixture and cross-runtime obligation

`tests/fixtures/proposed/scoring_contract_v2.json` contains language-neutral,
synthetic conformance cases only. Python tests cover canonical serialization,
strict decoding, source rebinding, state contradictions and invalid numeric
forms.

Tai's Kotlin environment must independently consume the canonical fixture and
produce identical canonical bytes, Decimal interpretation, ordering and
expected accept/reject results before Python/Kotlin conformance can be claimed.
A Python-only pass does not establish that result.

## 8. Explicitly deferred work

This package does not provide:

- an operational price-only evaluator;
- a scoring formula or learned model;
- scorer training, loading or inference;
- a real trusted registry, signature verifier or artifact resolver;
- calibrated probabilities or `Kappa`;
- `Phi`, PT1, PT2 or selective-verification thresholds;
- candidate selection or permanent-c0 replacement;
- controller, review, persistence or Android activation; or
- validation/held-out evaluation.

HC-D04, HC-D05 and HC-D13 remain unresolved. A structurally complete scoring
audit cannot settle those controller decisions.

## 9. Acceptance boundary

The implemented records and tests demonstrate structural consistency on
synthetic evidence. They do not establish scorer correctness, empirical
validity, artifact authenticity, real-backend readiness or evaluation freeze.
Independent Tai review and separate Git integration authorization remain
mandatory.
