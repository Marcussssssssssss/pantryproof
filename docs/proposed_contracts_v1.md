# PantryProof Proposed-System Contracts V1

Status: **PROVISIONAL DEVELOPMENT INTERFACE — NOT EVALUATION-FROZEN**

This document defines the shared Python boundary introduced by Task 2.3. It
implements the interface decisions approved in
`docs/proposed_method_traceability_v0.md`; it does not implement Algorithm 4.1.
The exact candidate algorithms, numerical configurations, resources, Android
transport, and persistence service remain future work.

## 1. Public modules and API

The public package is `pipeline.proposed`.

- `adapt_b2_to_proposed(b2_result, b3_result=None)` consumes an already-computed
  `B2ExtractionResult` and an optional compatible `B3Result`.
- `ProposedAdapterResultV1` records either method-ready fields or the preserved
  insufficient-source fallback.
- `ProposedAdapterIntegrityError` identifies corrupt or incompatible stored
  upstream records. A future orchestrator, not this adapter, maps that condition
  to `FAILED/PRE_RESOLUTION`.
- `to_json_compatible()` and `to_deterministic_json()` provide deterministic,
  language-neutral conformance serialization. They are not a database layer.

All V1 records are frozen, slotted dataclasses. Collections stored by these
records are tuples. No supposedly immutable record exposes a mutable dictionary.
Their version is `PROPOSED_CONTRACT_VERSION = "1"`.

The eight approved record families are:

1. `MethodReadyFieldV1`;
2. `CandidateProvenanceV1` and `CandidateRecordV1`;
3. `ConstraintResultV1`;
4. `CandidateEvidenceV1`;
5. `FieldDecisionV1`;
6. `ConfigurationRefsV1` (with typed `ConfigurationRefV1` leaves);
7. `ReviewResolutionV1`; and
8. `FinalApplicationOutcomeV1`.

Small supporting records are `SourceCharacterSpanV1`, `B3CompatibleSeedV1`,
and `PreliminaryRankV1`. `B3CompatibleSeedV1` is intentionally not a candidate
record.

Task 2.3A adds integrity corrections before Contract V1 has been independently
approved. Consequently the provisional version remains `"1"`, but two public
constructors are stronger: `FieldDecisionV1` now requires its complete
`MethodReadyFieldV1`, and `ReviewResolutionV1` now requires nonempty actor and
resolution-event references.

## 2. Source-of-truth c0 boundary

For every method-ready field:

```text
original_b2_field.value == original_value == c0_value
```

`MethodReadyFieldV1` retains the exact B2 `StructuredField` object, its field and
receipt identity, ordered source-token IDs, exact referenced OCR token objects,
source image ID, source-processing status, B2 extraction status/version, and
stored gate result. A method-ready `EXTRACTED` field requires that stored gate
result to be `SUFFICIENT`; an `INSUFFICIENT` result cannot be represented as a
`MethodReadyFieldV1`. This validates the stored decision without executing the
gate again and does not prove that the gate ran exactly once. Its stable
`c0_candidate_id` is permanent.

Only a B2 field with `FieldStatus.EXTRACTED` becomes method-ready. Missing or
unresolved fields remain in the B2 output and are listed by the adapter as
`excluded_b2_field_ids`; no value or candidate is fabricated for them. A
sufficient source package may legitimately produce a structurally `PARTIAL` or
`FAILED` B2 output. The adapter preserves that status and does not translate it
to `FALLBACK_NO_UPDATE`.

The adapter accepts only exact `B2-layout-graph-v0` structured output. It reads
the stored source gate and never invokes OCR, `sourceEvidenceSufficient()`, or
`extract_b2()`. A structured field without a stored `SUFFICIENT` gate is a
processing-integrity error, not ordinary source insufficiency. The adapter
cannot prove the gate was executed exactly once; that guarantee remains an
orchestrator responsibility.

## 3. B3 compatibility and seed separation

An optional B3 input must:

- retain the exact same `B2ExtractionResult` object;
- identify `B3-generic-rules-v0`;
- preserve receipt and exact source-evidence identity; and
- satisfy the existing B3 result invariants.

The B3-transformed field never becomes `c0`. A differing normalization or
source-supported B3 value is recorded as `B3CompatibleSeedV1`, with rule/event
IDs and genuine source character spans where B3 provides them. A B3 seed is only
input evidence for a future suspicion/candidate-generation stage. The adapter
does not construct `CandidateRecordV1`, apply `candidateLimit`, score, select, or
accept the seed. If B3 does not transform a field, the field still has permanent
`c0`.

The existing B2 and B3 outputs are never mutated. The adapter preserves B2 field
and row order and source-reference order.

For a B2 insufficient-source result, the adapter preserves the existing
`FALLBACK_NO_UPDATE` disposition and emits no fields or seeds. Contract V0 does
not carry an extractor-version field on this fallback shape, so exact B2 version
checking is possible only for structured output; the concrete
`B2ExtractionResult` type and fallback invariants are checked instead.

## 4. Candidate identity, provenance, ranking, and limit

`CandidateSourceKind` contains only thesis candidate-value sources:

1. `SOURCE_TOKEN_OR_NEIGHBOUR`;
2. `GENERIC_NORMALIZATION`;
3. `RETAILER_MAPPING`; and
4. `PANTRY_TERMINOLOGY`.

`ORIGINAL` identifies permanent `c0`. Price/reference evidence is deliberately
absent from this enum because it cannot generate a candidate value.

`CandidateProvenanceV1` preserves an ordered provenance-union member. Depending
on its source kind it can carry source token IDs, genuine half-open character
spans, source-order relationship/position, a generic rule ID, or a versioned
retailer/terminology resource snapshot. It rejects incompatible combinations;
offsets and resources are never invented. `SourceCharacterSpanV1.start` and
`.end` must be non-Boolean integers, form a nonempty half-open range, and satisfy
`len(text) == end - start`. This shape validation cannot by itself prove that
the text equals the corresponding OCR-token slice. Candidate-source and adapter
boundaries that possess the original token must additionally verify
`text == token.original_text[start:end]`.

`CandidateRecordV1` distinguishes `ORIGINAL` from `ALTERED`. It records the
originating receipt/field, permanent c0 identity, value, normalized deduplication
key, ordered provenance union, limit status, and optional future ranking output.
The altered-candidate ranking record has the required non-price components:
source priority, normalized edit similarity to c0, source-order displacement,
normalized text, rank position, and optional tie group. This contract records a
future ranking result but does not define the unresolved normalization,
similarity, displacement, limit, or tie algorithms.

`CandidateLimitStatus` is either `RETAINED` or `LIMIT_OVERFLOW`. Permanent c0
must always be `RETAINED` and is outside altered-candidate ranking. An overflow
candidate keeps rank/provenance plus a reason, but cannot receive
`CandidateEvidenceV1`. Therefore overflow metadata remains separate from the
post-limit hard-constraint/scoring audit.

## 5. Constraint and candidate-audit state

`ConstraintResultV1` joins receipt, field, and candidate identity to
`ELIGIBLE` or `CONSTRAINT_REJECTED`, evaluated rule IDs, typed reason codes, and
a required rejection detail. It records a result only; it performs no rule.

`CandidateEvidenceV1` embeds the retained candidate and its matching constraint
record. Its candidate status is one of:

- `SCORING_ELIGIBLE`;
- `CONSTRAINT_REJECTED`; or
- `REJECTED_PRICE_ONLY`.

A constraint-rejected candidate retains this audit entry but must have no
feature schema/vector/mask, raw score, or calibrated probability. Its score and
calibration statuses are `NOT_APPLICABLE`, and `probability_available` is false.
The same bypass applies to an altered `REJECTED_PRICE_ONLY` candidate. These
states cannot be marked scoring-eligible. A failed c0 remains a retained audited
candidate, but `FieldDecisionV1` cannot mark it `AUTO_ACCEPTED` because an
automatic decision must reference eligible, probability-available candidate
evidence.

Raw score and calibrated probability are separate nullable `Decimal` values.
Finite-value validation is mandatory; a present probability must be in `[0, 1]`.
An unavailable score or probability remains null and carries an explicit reason.
An available raw score requires a `READY` `Theta_A`; an available calibrated
probability requires both an available finite raw score under that `Theta_A` and
a `READY` `Kappa`. Calibration cannot be `AVAILABLE` when scoring is
`UNAVAILABLE`. An available raw score may legitimately have unavailable
calibration, and both may be unavailable with explicit reasons. These
validations do not assert that a model or calibrator is scientifically valid.

When the selected candidate's probability is unavailable, `FieldDecisionV1`
can freeze only the permanent original c0 and its exact B2 value. It cannot
freeze an altered candidate as the pre-review prediction. This structurally
protects Algorithm 4.1 line 16 for the selected evidence record. The future
policy/orchestrator must still inspect the complete required candidate set,
detect any unavailable required probability, revert selection to c0, set
`NOT_PERMITTED`, and route the field to `REVIEW_REQUIRED` before constructing
the decision.

## 6. Seven-slot feature boundary

`FEATURE_SCHEMA_ID_V1` is
`pantryproof-candidate-evidence-7-v1`. The immutable conceptual order is:

| Position | Slot | Concept | Required provenance class |
|---:|---|---|---|
| 1 | `q_o` | OCR evidence/confidence | Original OCR token evidence |
| 2 | `q_e` | Extractor evidence/confidence | Frozen B2 field/association |
| 3 | `a_l` | Lexical agreement | Candidate, c0, literal source, terminology |
| 4 | `a_y` | Layout/spatial agreement | B2 polygons and associations |
| 5 | `s_r` | Retailer support | Versioned retailer snapshot |
| 6 | `s_a` | Arithmetic support | Field/equation audit |
| 7 | `s_p` | Malaysian price/reference support | Versioned dated reference evidence |

For a scoring-eligible record, the slot tuple must match this order and the
feature values, per-slot provenance-reference tuples, and missingness mask must
each have length seven. Values are provisional typed scalars (`Decimal`, string,
Boolean, or null). A null value must have a true missingness flag and a present
value must have a false flag. In particular, unavailable price evidence is null
and missing—not numeric zero and not evidence of incorrectness.

No final encodings, normalizations, coefficients, scorer family, or imputation
rules are selected by this interface.

## 7. Configuration separation

`ConfigurationRefsV1` always contains five typed, non-interchangeable references:

- `Theta_A`: candidate/scorer/replacement configuration;
- `Kappa`: calibration configuration;
- `Phi`: selective-verification policy configuration;
- `PT1`: automatic-comparison operating configuration; and
- `PT2`: selective-policy operating configuration.

Each reference has an ID, version, optional content hash, state, and reason.
`READY` requires a content hash. `NOT_READY` and `NOT_VALID` require a reason.
`NO_VALID_POINT` is valid only for PT2 and represents the thesis-defined
validation outcome; it is not a threshold. The interface deliberately contains
no fabricated candidate limit, model family, margin, threshold, or calibration
method.

A `READY` `Kappa` with an unavailable probability and explicit reason records a
per-field runtime calibration failure. A configuration-level `NOT_READY` or
`NOT_VALID` state is different: it remains visible in the configuration
reference and must block applicable held-out probability-dependent execution.
It must not be relabelled as the Algorithm 4.1 line-16 runtime path. Enforcing
that execution boundary across the complete candidate set remains an
orchestrator responsibility.

The exact `ConfigurationRefsV1` stored on a `FieldDecisionV1` must equal the
immutable configuration bundle on its selected `CandidateEvidenceV1`. This
prevents a decision from being attributed to a different `Theta_A`, `Kappa`, or
`Phi`. `AUTO_ACCEPTED` additionally requires `Phi` to be `READY`. PT1 and PT2
remain evaluation/operating references and are not both required to be `READY`
for a valid field decision; PT2 may explicitly be `NO_VALID_POINT`.

## 8. Field, receipt, review, and persistence separation

`FieldDecisionV1` embeds the complete immutable `MethodReadyFieldV1`, rather
than trusting copied c0 strings. Receipt ID, field ID, method-field ID, c0
candidate ID, and c0 value must all match that original record. The selected
candidate must point to the same c0. Therefore an altered B3 seed or transformed
value cannot silently replace the original B2 c0. The decision also freezes the
matching selected candidate/evidence audit, pre-review predicted value,
field-level decision, automatic-commit permission, reason, cached
unresolved-conflict result when available, and matching configuration references.

`AUTO_ACCEPTED` is a field-level state. It requires `PERMITTED`, a cached
no-conflict result, and eligible probability-available selected evidence.
`REVIEW_REQUIRED` requires `NOT_PERMITTED`. If its selected evidence has no
available calibrated probability, its selected candidate and frozen prediction
must be the permanent original B2 c0. Neither state is the receipt-level
`AUTO_RESOLVED` disposition.

`ReviewResolutionV1` may be:

- evaluation-only `ORACLE_POLICY_RESOLVED`;
- actual `USER_CONFIRMED`;
- actual `USER_MODIFIED`; or
- actual `USER_REJECTED`.

It may resolve only a frozen `REVIEW_REQUIRED` decision and always retains the
actually presented pre-review value. Confirmation keeps that value, modification
records a different value, and rejection has no resolved value. Every resolution
requires both a nonempty `actor_reference` and `resolution_event_id`, so the
record denotes a realized Tier A oracle or Tier B user action rather than a
hypothetical proposal. The resolution kind retains the oracle/user distinction;
oracle output is never production-persistence eligible.

`FinalApplicationOutcomeV1` embeds the frozen Contract V0
`PreResolutionDisposition`; later transaction status cannot overwrite it.
`FALLBACK_NO_UPDATE` and `FAILED/PRE_RESOLUTION` cannot attempt persistence.
`AUTO_RESOLVED` may attempt persistence only when its supplied field decisions
are all eligible automatic acceptances. `REVIEW_REQUIRED` may attempt only when
every supplied review-required decision has a realized `USER_CONFIRMED` or
`USER_MODIFIED` record. Oracle or rejected/unresolved user review cannot commit.
One receipt field may appear in at most one supplied field decision, and one
frozen review-required decision may have at most one finalized resolution.
Every resolution must bind to a supplied decision with the same decision ID and
equal complete immutable content; matching an ID while changing decision content
is rejected. Unbound, duplicated, or contradictory resolutions therefore cannot
authorize `COMMITTED`.

`NOT_ATTEMPTED` is distinct from permission. `COMMITTED` structurally requires a
persistence-attempt ID, inventory-write reference, and successful-persistence
evidence reference. `FAILED` requires `INVENTORY_PERSISTENCE`, an attempt ID,
and reason, and cannot contain successful-write evidence. These checks still do
not prove a database transaction occurred: a future persistence service may
construct `COMMITTED` only after verified transaction success. No SQLite code is
implemented here.

Completeness of a future receipt's required field-decision set remains an
orchestrator responsibility. The record verifies all decisions supplied to it;
the future orchestrator must prove that the tuple is complete before persistence.

## 9. Serialization conformance fixture

`tests/fixtures/proposed/b2_c0_b3_seed_v1.json` is synthetic and contains no real
receipt data. It freezes representative cross-component IDs, enum spellings,
nulls, source references, a permanent full-width B2 c0 value, the distinct
ASCII-normalized B3 seed, exact source slice, and a Decimal string.

Serialization rules are:

- enums become their declared string values;
- tuples become JSON arrays in original order;
- dataclass field names are retained;
- null remains JSON `null`;
- `Decimal` becomes a decimal string, never a binary floating-point number; and
- object keys are sorted with compact deterministic separators.

The fixture checks Python-side conformance only. A future Dart/Kotlin consumer
must reproduce the same IDs, ordering, null semantics, and decimal strings.
The existing adapter fixture contains neither a field decision nor a review
resolution, so Task 2.3A does not alter its bytes. Future fixtures containing
those records must include the embedded method-ready original and mandatory
actor/event fields.

## 10. Two-member ownership boundary

After independent review of this provisional interface:

- Team Member A may consume `MethodReadyFieldV1` and B3 seeds to implement
  suspicion, candidate generation/deduplication/limit, typed provenance, and
  hard-constraint results. Member A must not assign features, scores,
  probabilities, field decisions, review, or persistence outcomes.
- Team Member B may consume retained `CandidateRecordV1` and
  `ConstraintResultV1` to implement the seven-slot evidence boundary, scorer,
  calibration, replacement/policy decisions, and PT1/PT2 configuration results.
  Member B must not alter c0, candidate provenance, limit status, or hard-
  constraint results.
- Shared/orchestrator work owns exactly-once gate execution, receipt disposition
  aggregation, completeness checks, review routing, and persistence-service
  invocation.

Neither member should edit these shared interfaces independently. A schema
change requires a coordinated version bump, updated cross-component fixture,
both test suites, and traceability review.

## 11. Deliberately unimplemented decisions

The following remain unresolved and are not hidden in this contract:

- executable source-gate thresholds/fault policy and orchestration;
- suspicion detection;
- candidate normalization, edit similarity, source displacement, deduplication,
  numerical `candidateLimit`, overflow tie rule, and selection;
- hard-constraint grammars, rule catalogue, arithmetic tolerances/exceptions;
- seven feature encodings, ranges, normalization, and missing-value treatment;
- scorer family, training objective, parameters, and deterministic score tie rule;
- calibration method and validation fitting;
- replacement margin, acceptance threshold, conflict tolerance, PT1/PT2 grids
  and validation-selection implementations;
- retailer, terminology, and Malaysian price resources/snapshot coverage;
- receipt-decision aggregation and full review workflow;
- Android transport/runtime, SQLite schema, transaction service, and security;
  and
- formal B2/B3/config/resource/data hashes required for evaluation freeze.

The records validate structural consistency only. Synthetic tests demonstrate
interface behavior, not extraction accuracy, calibrated correctness, model
quality, or thesis results.

## 12. Version and change control

Contract V1 is provisional and does not modify Contract V0, B1, B2, B3, their
tests, or their manifests. The Task 2.3A constructor corrections occurred before
independent approval and therefore replace the unapproved draft under the same
version. Version `1` may be used for parallel development only after review.
After approval, any incompatible field, enum, identity, nullability, ordering,
or state-transition change requires a new record version and fixture revision.

The development interface is **not evaluation-frozen** until the remaining
algorithms/configurations/resources are selected through the declared
training/validation route and the implementation/fixture hashes are recorded.
