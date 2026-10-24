# Proposed Hard-Constraint Audit Contract V2

Status: provisional G1 implementation with the bounded G1R1 and G1R2
integrity corrections, for independent review.

This document describes the immutable, structural audit records implemented in
`pipeline/proposed/hard_constraint_contracts_v2.py`. The module is an isolated
Contract V2 layer. It does not alter Contract V1 and it is not exported through
`pipeline.proposed`.

## G1R1 correction summary

The independent G1 audit identified three boundary inconsistencies. G1R1 makes
only these corrections:

1. Direct V2 construction now applies exact, non-Boolean integer validation to
   nested V1 rank fields, provenance source-order positions and source-span
   offsets before JSON serialization.
2. The live D3 factory validates complete rule-result structure before aggregate
   computation, so missing, extra, duplicate and reordered outcomes raise
   `HardConstraintAuditIntegrityError`; live source identity failures continue
   to raise `HardConstraintSourceBindingError`.
3. Every documented negative fixture case now declares a deterministic
   operation, validation boundary and expected exception, and the focused suite
   executes all eight cases.

These changes do not alter the six enums, aggregation policy, permanent c0,
Contract V1 coexistence or any downstream methodology boundary.

G1R2 adds one source-bound consistency check: the V2 profile's complete
`theta_a_reference` must equal the frozen `theta_a_ref` exposed by the supplied
live D3 hard-constraint input. A difference in configuration kind, ID, version,
state, declared content hash, status reason, record version or any other stored
`ConfigurationRefV1` field raises `HardConstraintSourceBindingError`.

## 1. Method boundary

Algorithm 4.1 requires hard constraints to be checked before candidate feature
construction, scoring, calibration and automatic selection. Contract V2 records
the outcome of those checks for one retained candidate. It does not implement a
hard-rule predicate, arithmetic rule, eligibility controller, feature builder,
scorer, calibrator, selector, review router or persistence service.

The permanent B2 candidate remains `c0`. An altered candidate is always linked
to that complete V1 `CandidateRecordV1`; it never replaces or rewrites `c0`.

## 2. Enumerations

The public V2 enumerations are:

- `RuleRequirementV2`: `MANDATORY`, `OPTIONAL`.
- `RuleOutcomeStateV2`: `PASS`, `FAIL`, `NOT_APPLICABLE`, `UNAVAILABLE`.
- `RuleEvidenceAvailabilityV2`: `AVAILABLE`, `UNAVAILABLE`,
  `NOT_APPLICABLE`.
- `ConstraintAggregateStateV2`: `ELIGIBLE`, `CONSTRAINT_REJECTED`,
  `CONSTRAINT_UNAVAILABLE`.
- `ConstraintAggregateReasonV2`:
  `ALL_APPLICABLE_MANDATORY_RULES_PASSED`, `MANDATORY_RULE_FAILED`,
  `MANDATORY_RULE_UNAVAILABLE`, `NO_APPLICABLE_MANDATORY_RULE`.
- `RuleOutcomeReasonKindV2`: `FAILURE`, `UNAVAILABILITY`,
  `PROFILE_EXCLUSION`, `APPROVED_EXCEPTION`.

Rule IDs, resource kinds and reason codes use the stable syntax
`[A-Z][A-Z0-9_]*`. Their vocabulary is structural in G1; no semantic rule
catalogue is approved by this module.

## 3. Immutable records

All V2 records are frozen, slotted dataclasses with `record_version = "2"`.

The public stored fields are exact and versioned:

| Record | Stored constructor fields (in declaration order) |
|---|---|
| `HardConstraintResourceRefV2` | `resource_reference_id`, `resource_kind`, `resource_id`, `resource_version`, `declared_content_reference`, `declared_content_hash`, `record_version` |
| `HardConstraintRuleSpecV2` | `rule_id`, `rule_version`, `position`, `requirement`, `applicability_reference`, `resource_reference_ids`, `record_version` |
| `HardConstraintProfileRefV2` | `profile_id`, `profile_version`, `theta_a_reference`, `ordered_rule_specs`, `resource_references`, `declared_content_hash`, `record_version` |
| `EvidenceReferenceV2` | `reference_namespace`, `reference_id`, `source_record_version`, `record_version` |
| `ConstraintRuleOutcomeV2` | `rule_outcome_id`, `receipt_id`, `field_id`, `candidate`, `c0_candidate`, `rule_spec`, `state`, `attempted`, `evidence_availability`, `evidence_references`, `outcome_reason_kind`, `outcome_code`, `outcome_detail`, `theta_a_reference`, `rule_profile_reference`, `resource_references`, `record_version` |
| `ConstraintResultV2` | `constraint_result_id`, `receipt_id`, `field_id`, `candidate`, `c0_candidate`, `theta_a_reference`, `rule_profile_reference`, `rule_outcomes`, `aggregate_state`, `aggregate_reason`, `record_version` |

### `HardConstraintResourceRefV2`

Records a resource-reference ID, resource kind, resource ID, resource version,
declared content reference and optional declared content hash. A reference is
provenance metadata, not proof that the resource bytes exist or match the
declared hash.

### `HardConstraintRuleSpecV2`

Records a rule ID and version, zero-based profile position, mandatory/optional
requirement, applicability reference and ordered resource-reference IDs.

### `HardConstraintProfileRefV2`

Records the profile ID/version, READY `Theta_A` V1 reference, ordered rule
specifications, ordered resource references and optional declared profile hash.
Rule positions must be contiguous and unique. Rule IDs and resource IDs must be
unique. Every rule resource must resolve, follow profile resource order and be
used by at least one rule.

G1 treats a profile with no rules or no mandatory rules as invalid
configuration. This is distinct from a valid profile whose mandatory rules all
produce `NOT_APPLICABLE` for one candidate.

### `EvidenceReferenceV2`

Records an evidence namespace, evidence ID and optional source-record version.
It identifies evidence claimed by an outcome but does not by itself prove that
the evidence object or source bytes exist.

### `ConstraintRuleOutcomeV2`

Records exactly one declared rule outcome for one retained candidate. It embeds
the complete candidate and permanent `c0` records, the exact profile rule by
immutable content, state, attempt flag, evidence availability, ordered evidence
references, optional typed reason information, `Theta_A`, profile and declared
resource references.

### `ConstraintResultV2`

Records a complete ordered rule audit for one candidate and its recomputed
aggregate state/reason. It is candidate-level only. It does not represent all
retained candidates for a field and cannot prove field-wide completeness.

## 4. Rule-state invariants

| State | `attempted` | Evidence availability | Reason fields |
|---|---:|---|---|
| `PASS` | `true` | `AVAILABLE` | all absent |
| `FAIL` | `true` | `AVAILABLE` | `FAILURE` and code required |
| `NOT_APPLICABLE` | `false` | `NOT_APPLICABLE` | `PROFILE_EXCLUSION` or `APPROVED_EXCEPTION`, plus code |
| `UNAVAILABLE` | `true` or `false` | `UNAVAILABLE` | `UNAVAILABILITY` and code required |

`NOT_APPLICABLE` means the primary hard-rule predicate was not attempted. An
applicability or approved-exception check may already have inspected runtime
evidence. Exception-qualified non-applicability is kept explicit and is never
encoded as an ordinary `PASS`.

G1 intentionally does not require evidence references for every state. Whether
particular semantic rules require operand, exception or external-resource
references remains pending under the later rule-policy decisions. Empty
references therefore mean “no structural reference supplied”, not proof that no
evidence was inspected.

## 5. Aggregate truth table

Only mandatory rule outcomes determine the aggregate. Optional failures or
unavailability remain audited but do not alter it.

| Valid mandatory outcomes | Aggregate state | Aggregate reason |
|---|---|---|
| Any `FAIL` | `CONSTRAINT_REJECTED` | `MANDATORY_RULE_FAILED` |
| No `FAIL`, at least one `UNAVAILABLE` | `CONSTRAINT_UNAVAILABLE` | `MANDATORY_RULE_UNAVAILABLE` |
| At least one `PASS`, all others `PASS` or `NOT_APPLICABLE` | `ELIGIBLE` | `ALL_APPLICABLE_MANDATORY_RULES_PASSED` |
| All `NOT_APPLICABLE` | `CONSTRAINT_UNAVAILABLE` | `NO_APPLICABLE_MANDATORY_RULE` |

Mandatory failure has precedence over mandatory unavailability. The aggregate
is recomputed during construction and reconstruction; callers cannot supply a
contradictory state or reason.

## 6. Audit completeness

A valid candidate audit contains exactly one outcome for every profile rule,
including optional and `NOT_APPLICABLE` rules, in declared profile order.

- A missing rule outcome is an integrity error, not `UNAVAILABLE`.
- A duplicate outcome or outcome ID is an integrity error.
- An unexpected extra outcome is an integrity error.
- Reordered outcomes are an integrity error.
- A present rule outcome with state `UNAVAILABLE` is legitimate audited
  candidate-level unavailability.
- An invalid profile is a configuration error, not candidate unavailability.

The record cannot prove that a semantic evaluator actually executed. It can
only validate the completeness and internal consistency of the recorded audit.

## 7. Candidate and permanent-c0 binding

Both `ConstraintRuleOutcomeV2` and `ConstraintResultV2` embed complete immutable
`CandidateRecordV1` records rather than candidate IDs alone. Construction
revalidates the candidate, its complete ordered provenance union, source spans
and preliminary rank.

At this boundary, `PreliminaryRankV1.source_priority_rank`,
`source_order_displacement`, `rank_position`, non-null
`CandidateProvenanceV1.source_order_position`, and
`SourceCharacterSpanV1.start`/`end` must have exact Python type `int`. Because
`bool` is an `int` subclass in Python, an `isinstance(value, int)` check is not
sufficient. Boolean values are rejected rather than coerced to zero or one.
This closes the direct-constructor/JSON-reader mismatch while leaving legitimate
integers and Decimal scale unchanged.

The audited candidate and `c0` must share receipt and field identity. The
candidate's `c0_candidate_id` must identify the supplied retained ORIGINAL
candidate. If the audited candidate is ORIGINAL, its complete record must equal
the supplied `c0` record. Altered V1 candidates remain altered and retain their
own provenance and rank.

## 8. Live D3 source binding

`build_source_bound_constraint_result_v2(...)` is the optional live integration
boundary. It requires:

- an existing `HardConstraintOperandAuditResultV0`;
- the exact `CandidateOperandAuditV0` member of that aggregate (`is`);
- the exact retained D3 candidate object and exact c0-first candidate object;
- rule outcomes carrying those exact candidate objects; and
- complete immutable profile equality; and
- complete immutable equality between the profile's `Theta_A` reference and
  the upstream `HardConstraintInputResultV0.theta_a_ref`.

This factory rejects a value-equal copied D3 candidate audit. The standalone
record constructor, by contrast, checks complete immutable content equality.
That is necessary for cross-runtime reconstruction: Python object identity does
not survive JSON serialization.

`Theta_A` uses complete content equality rather than Python object identity. A
distinct `ConfigurationRefV1` object with identical stored fields is therefore
accepted. Standalone construction and JSON reconstruction validate only the
internal agreement among the V2 profile, outcomes and aggregate; they do not
have a live D3 graph against which to verify the upstream `Theta_A` choice.

Before aggregate computation, the factory applies the same complete ordered
rule-audit validation as the standalone aggregate. Missing, extra, duplicate or
reordered outcomes therefore fail through `HardConstraintAuditIntegrityError`,
not a raw `ValueError` from strict tuple iteration. Exact D3 membership or
object-identity failures remain `HardConstraintSourceBindingError`.

Neither boundary cryptographically authenticates provenance. A coordinated
mutation of upstream records and all associated private integrity metadata is
outside the claim. G1 also does not authenticate the B2 result, B3 execution,
`Theta_A` manifest or external resource bytes beyond the checks already offered
by upstream records.

## 9. D3 evidence availability versus V2 rule unavailability

D3 raw operand availability preserves original B2 states:

- `AVAILABLE`
- `MISSING`
- `UNRESOLVED`
- `NOT_APPLICABLE`

V2 does not add a new D3 operand state. `RuleOutcomeStateV2.UNAVAILABLE` is a
separate, derived hard-rule audit outcome. A future evaluator may derive it from
one or more permitted observations, but G1 does not define that semantic
mapping. Original B2 `MISSING` and `UNRESOLVED` evidence must remain visible in
D3 rather than being rewritten as a new upstream state.

## 10. Configuration and resource provenance

Profiles require a V1 `ConfigurationRefV1` whose kind is `THETA_A` and state is
`READY`. Each outcome and aggregate must carry equal `Theta_A` and profile
content. Rule resources must equal the ordered profile subset declared by that
rule.

Declared IDs, versions, content references and hashes make configuration and
resource claims auditable. They do not authenticate source bytes, prove that a
hash was computed correctly, or provide a validation-frozen manifest. Such
authentication requires a later coordinated boundary. G1R2 equality with the
D3 reference prevents contradictory stored configuration claims but does not
authenticate the declared hash or its referenced bytes.

## 11. Serialization contract

`constraint_result_v2_to_json(...)` emits deterministic UTF-8-compatible JSON:

- object keys are lexicographically sorted;
- separators are compact and stable;
- tuple order is preserved as JSON-array order;
- enum values use their exact string values;
- `Decimal` values are base-10 strings, retaining significant trailing zeros;
- optional absent values are explicit `null`; and
- non-finite numbers are unsupported.

`constraint_result_v2_from_json(...)` is strict. It rejects malformed JSON, a
UTF-8 BOM, missing fields, unknown fields, unsupported versions, unknown enums,
Boolean-as-integer fields and numeric JSON values where Decimal strings are
required. Successful reconstruction reruns all nested V1 and V2 invariants.

The language-neutral fixture is
`tests/fixtures/proposed/hard_constraint_contract_v2.json`. It contains a full
altered-candidate positive record, explicit null and Decimal examples, and a
catalogue of adversarial mutations expected to fail. Fixture version
`hard-constraint-v2-fixture-v2` gives every negative case:

- a stable operation code;
- one of `JSON_DESERIALIZATION`, `STANDALONE_CONSTRUCTOR` or
  `LIVE_D3_FACTORY` as its boundary;
- the exact expected exception type; and
- a language-neutral claim explaining the mutation.

The Python conformance tests execute all eight operations. JSON reconstruction
cases expect `HardConstraintSerializationError`, which is the documented wrapper
around nested record failures. Standalone cases retain their profile or
audit-integrity exception. The live copied-D3 case expects a source-binding
exception. Valid JSON is not rejected merely because it cannot recover Python
object identity.

## 12. Failure taxonomy

- `HardConstraintProfileConfigurationError`: malformed profile, rule ordering,
  mandatory-rule declaration, `Theta_A` or resource relationships.
- `HardConstraintAuditIntegrityError`: malformed or contradictory candidate,
  c0, rule outcome, audit completeness or aggregate.
- `HardConstraintSourceBindingError`: live D3 exact-reference failure.
- `HardConstraintSerializationError`: invalid JSON shape, value or reconstructed
  record.

These exceptions distinguish integrity/configuration failures from a legitimate
recorded `CONSTRAINT_UNAVAILABLE` result.

## 13. Compatibility boundary

Contract V1 remains unchanged. G1 does not project V2 into
`ConstraintResultV1`; in particular, it never maps `CONSTRAINT_UNAVAILABLE` to
V1 `OTHER`, eligibility or rejection. Any future projection requires an
explicit approved mapping for every V2 state and reason, full V1 constructor
conformance, provenance-loss review and fail-closed handling for unrepresentable
information.

No V2 type is added to package exports. Consumers must import this provisional
module explicitly and handle its version explicitly.

## 14. Downstream safety boundary

`ELIGIBLE` is a structural hard-constraint outcome only. It is not permission
to score, auto-accept, review-resolve or persist. `CONSTRAINT_REJECTED` and
mandatory `CONSTRAINT_UNAVAILABLE` are audit states; this module does not invoke
feature construction or decide later controller behavior.

One `ConstraintResultV2` cannot prove that every retained candidate received an
audit, that candidates are c0-first at field level, or that no candidate audit
was omitted. Those checks belong to a later coordinated field-wide evaluator or
controller aggregate.

## 15. Deferred decisions

G1 intentionally leaves these methodology questions unresolved:

- concrete hard-rule semantics and arithmetic tolerances;
- rule-specific applicability and approved-exception policies;
- which evidence references are mandatory for each semantic rule;
- authenticated profile, `Theta_A` and resource snapshots;
- original-c0 rejection or unavailability controller behavior;
- behavior for nonselected altered candidates with unavailable constraints;
- field-wide audit completeness and candidate-level execution proof;
- feature construction, scoring, calibration, selection and review routing;
- Contract V2-to-V1 projection; and
- persistence eligibility.

The implemented schema follows the G1-authorized structural portions of
HC-D01, HC-D02, HC-D03, HC-D09, record-only HC-D10 and HC-D11. It does not claim
approval for HC-D04 through HC-D08, HC-D12 or HC-D13, nor for semantic rules
that depend on those decisions.

## 16. Synthetic verification scope

The focused tests cover:

- frozen records and complete original/altered candidate binding;
- all aggregate truth-table branches and mandatory precedence;
- optional-rule non-veto behavior;
- explicit approved-exception non-applicability;
- missing, duplicate, unexpected and reordered rule outcomes;
- invalid profiles, rule codes, positions and resource references;
- candidate/c0, profile, `Theta_A` and resource contradictions;
- D3 `MISSING`/`UNRESOLVED` separation from V2 `UNAVAILABLE`;
- exact live D3 object binding and copied-object rejection;
- standalone cross-runtime content reconstruction;
- strict deterministic JSON, Decimal strings, nulls and fixture conformance;
- exact non-Boolean validation for every serialized nested V1 integer;
- typed live-factory rejection for incomplete or contradictory rule sets;
- live D3/profile `Theta_A` equality checks, including ID, version and declared
  hash mismatch rejection while accepting value-equal distinct objects;
- execution of every negative fixture mutation at its declared boundary; and
- absence of downstream evidence, decision, calibration, review and persistence
  construction.

All fixtures are synthetic. No real receipts, held-out data, external resources
or model inference are used.
