# Proposed Hard-Constraint Outcome Contract Change V2

## 1. Status: PROPOSAL — NOT APPROVED

This document is a coordination proposal only. It does not freeze a methodology,
authorize production implementation, alter Contract V1, or authenticate any
configuration. Every recommendation marked `PENDING SHARED APPROVAL` requires
the review sequence in Section 15 before implementation.

Repository state verified before authoring:

- branch: `feature/self-correction`;
- local and remote-tracking HEAD: `a6545373f8e9059f7c5adea9dce3e0a3b038e1e9`;
- frozen shared foundation `36e6cef` remains an ancestor;
- working tree and index were clean;
- no branch operation was performed.

## 2. Executive decision summary

The completed input context and operand audit preserve the evidence needed by a
future hard-constraint evaluator, but Contract V1 cannot represent a retained
candidate whose mandatory constraint cannot be determined. Its
`ConstraintEligibility` has only `ELIGIBLE` and `CONSTRAINT_REJECTED`, while
`CandidateEvidenceV1` requires one of those results. Treating unavailable
evidence as either state would create a false claim.

Two designs were assessed:

- **Option A - coordinated shared Contract V2:** add a four-state per-rule audit,
  a three-state candidate aggregate, strong candidate/profile/resource binding,
  and corresponding downstream audit support.
- **Option B - Contract V1 plus a separate pre-evidence audit:** keep unavailable
  results outside V1. This is smaller locally, but V1 cannot preserve that state
  through candidate evidence, field decisions, deterministic interchange, and
  Android consumption without an additional parallel decision contract.

**Recommended direction: Option A, PENDING SHARED APPROVAL.** It is the smallest
coherent shared change that preserves every retained candidate's audit across
the later scoring and decision boundaries. Option B may be useful as a temporary
research diagnostic, but it is not recommended as the final shared interface.

No hard-rule catalogue, grammar, tolerance, exception policy, profile hash, or
route for an unavailable/rejected permanent `c0` is approved by this proposal.

## 3. Authority and evidence matrix

| Topic | Verified source | Authority and finding |
|---|---|---|
| Candidate hard checks | Moderated thesis Section 3.4.4; Section 4.3; Tables 4.5-4.6 | `THESIS_REQUIRED`: retained candidates receive hard checks involving field/type, source/layout/association, and applicable arithmetic evidence. |
| Rejected altered candidate | Algorithm 4.1 lines 7-9; Table 4.6 | `THESIS_REQUIRED`: retain the audit and rejection reason; bypass feature construction, scoring, and calibration. |
| Permanent original | Section 4.3; Algorithm 4.1; `docs/proposed_method_traceability_v0.md` | `THESIS_REQUIRED`: original B2 output is permanent `c0`; it is audited and never deleted or silently replaced. |
| Probability fallback | Algorithm 4.1 lines 16-17 | `THESIS_REQUIRED`: unavailable required probability freezes `c0` and denies automatic commitment; missing valid `c0` probability at the later assertion is an execution failure. This does not itself resolve an earlier unavailable hard constraint. |
| Selected ineligible candidate | Algorithm 4.1 line 21 and postscript | `THESIS_REQUIRED`, with an unresolved interaction: an ineligible selected value cannot auto-commit; failed `c0` remains retained. Exact controller routing needs approval. |
| Optional price reference | Section 3.4.4; Tables 4.6-4.7; traceability document | `THESIS_REQUIRED`: price evidence cannot generate a candidate, and missing price evidence is neither hard-rule failure nor negative ground truth. Price-only rejection is a later, separate policy result. |
| Arithmetic exceptions | Section 3.4.4; Tables 4.7 and 4.10 | `THESIS_REQUIRED` at category level: weighted goods, promotions, discounts, missing unit prices, and similar exceptions need explicit policy. Exact rules remain unresolved. |
| Existing shared records | `pipeline/proposed/contracts.py`; `docs/proposed_contracts_v1.md` | `IMPLEMENTED`: immutable V1 records and deterministic serialization enforce current two-state constraint and downstream invariants. |
| Verified evaluator inputs | `pipeline/proposed/hard_constraint_context.py`; `pipeline/proposed/hard_constraint_operands.py`; their V0 documents and tests | `IMPLEMENTED`: exact retained candidates, pre-review B2 source, sufficient stored gate, raw operands, and availability are preserved without deciding eligibility. |
| B3 policies | `pipeline/baseline_b3.py`; `docs/baseline_b3_v0.md`; `docs/b3_freeze_manifest_v0.yaml` | `PROVISIONAL IMPLEMENTATION EVIDENCE`: useful policy candidates exist, including Decimal arithmetic, `ROUND_HALF_UP`, `0.01`, weighted-unit, and adjustment handling. They are not approved proposed-method rules or authenticated `Theta_A`. |
| This document | This proposal | `PROVISIONAL DESIGN`: names, state precedence, and migration plan below are recommendations, not frozen requirements. |

## 4. Existing Contract V1 invariants

The following are constructor-enforced facts, not proposed changes:

1. `ConstraintEligibility` contains only `ELIGIBLE` and
   `CONSTRAINT_REJECTED`.
2. `ConstraintResultV1` binds receipt, field, and candidate IDs, requires a
   nonempty unique `evaluated_rule_ids`, forbids reasons for eligible results,
   and requires a `ConstraintReasonCode` for rejection.
3. `ConstraintResultV1` does not embed the immutable candidate, rule versions,
   resources, a profile reference, or an explicit unavailable state.
4. `CandidateRecordV1` protects immutable candidate content, permanent `c0`,
   provenance, rank, and limit status. An original candidate must be retained,
   use `ORIGINAL`, equal `c0`, and remain outside altered-candidate ranking.
5. `CandidateEvidenceV1` embeds the complete `CandidateRecordV1` and matching
   `ConstraintResultV1`; receipt/field/candidate identities must match.
6. A constraint-rejected `CandidateEvidenceV1` must use a rejected audit status,
   omit all seven features, raw score, and probability, set their statuses to
   `NOT_APPLICABLE`, and set `probability_available` false.
7. A nonrejected evidence record requires `ELIGIBLE` and the complete seven-slot
   feature boundary. Raw score and calibration availability are separately
   validated; calibrated probability requires an available raw score and ready
   `Theta_A` and `Kappa` references.
8. `FieldDecisionV1` embeds its actual `MethodReadyFieldV1` and selected
   `CandidateEvidenceV1`. It rebinds receipt, field, method-field, `c0` ID/value,
   candidate content, and the exact `ConfigurationRefsV1` bundle.
9. `AUTO_ACCEPTED` requires an eligible selected candidate, available
   probability, permitted automatic commitment, no unresolved conflict, and a
   ready `Phi`. Unavailable selected probability can freeze only the original
   B2 `c0` and route `REVIEW_REQUIRED` with commitment not permitted.
10. `FinalApplicationOutcomeV1` preserves the frozen pre-resolution state,
    rejects duplicate fields/resolutions, binds full decision records, and
    permits persistence only for valid auto-resolved or actually user-resolved
    paths.
11. `ConfigurationRefV1` records kind, ID, version, readiness, and a nonempty
    content hash for ready configurations. Structural validation does not prove
    that the hash is authentic or that the referenced bytes were loaded.
12. All shared records require `record_version == "1"`. Serialization recursively
    emits enum values, finite `Decimal` values as strings, tuple/list values as
    arrays, explicit nulls for dataclass fields, sorted object keys, compact
    separators, and UTF-8-compatible JSON text.

Actual incompatibility: `UNAVAILABLE` exists for score/calibration values but
not for constraint eligibility. It therefore cannot be reused to describe an
undetermined mandatory hard rule without revising the constraint and candidate
audit boundary.

## 5. Contract-design alternatives and tradeoffs

| Criterion | Option A: coordinated Contract V2 | Option B: V1 plus separate pre-evidence audit |
|---|---|---|
| Every retained candidate audited | One ordered V2 audit set covers eligible, rejected, and unavailable candidates. | Possible before V1, but an unavailable candidate cannot enter `CandidateEvidenceV1`. |
| Candidate binding | V2 embeds the complete immutable `CandidateRecordV1` or a semantically identical successor. | Separate audit can embed it, but V1 later binds only copied IDs in `ConstraintResultV1`. |
| Profile/resource binding | Native V2 fields can bind exact `Theta_A`, rule profile, and resource snapshots. | Must live in a parallel record and is not bound by `CandidateEvidenceV1` or `FieldDecisionV1`. |
| Scoring bypass | Explicit for both rejected and constraint-unavailable candidates. | Rejection works in V1; unavailable needs an out-of-band block. |
| Field-level non-committable state | Can be carried into a coordinated V2 field decision. | V1 has no selected constraint-unavailable evidence; another wrapper/decision type is still required. |
| Android/interchange | One versioned schema and conformance fixture family. | Consumers must join two schemas and prove the join is complete and untampered. |
| Change size | Larger shared review and migration. | Smaller first local component, but complexity moves downstream and becomes a de facto second contract. |
| V1 regression risk | Managed by coexistence; V1 unchanged. | Low immediate V1 risk, higher risk of audit loss or contradictory projection. |
| Methodological honesty | Represents unavailable mandatory evidence without calling it pass or fail. | Safe only if unavailable candidates stop before V1; unsafe if projected as eligible/rejected. |

Option B is viable only as a temporary diagnostic boundary that never claims a
complete shared decision. To satisfy the full pipeline it would still need a
typed field-level non-committable outcome, binding to the separate audit, and a
cross-runtime schema. That duplicates much of Option A.

## 6. Recommended provisional architecture

**PENDING SHARED APPROVAL:** introduce a coordinated V2 outcome family while
retaining stable upstream V1 value objects where their meanings do not change.

```text
HardConstraintOperandAuditResultV0
        |
        v
authenticated/ready hard-rule profile check
        |
        +-- invalid profile/configuration --> configuration failure, no candidate result
        |
        v
ordered ConstraintRuleOutcomeV2 records for one retained candidate
        |
        v
ConstraintResultV2 (candidate-bound aggregate)
        |
        +-- ELIGIBLE ----------------------> features / score / calibration
        +-- CONSTRAINT_REJECTED ----------> audited bypass
        +-- CONSTRAINT_UNAVAILABLE --------> audited bypass, non-committable
        |
        v
CandidateEvidenceV2 -> FieldDecisionV2 -> receipt orchestration
```

The evaluator must process only `HardConstraintInputResultV0.candidates`; limit
overflow records remain in the upstream ledger and never receive candidate
constraint evidence. The profile validator must run before semantic evaluation.
An unexpected evaluator exception is a processing failure, not a candidate
constraint state.

Stable records proposed for reuse: `CandidateRecordV1`, `ConfigurationRefV1`,
`ConfigurationRefsV1`, `MethodReadyFieldV1`, and upstream context/operand V0
records. Records whose semantics must change: constraint result, candidate
evidence, and likely field decision. Final receipt outcome may need a V2 type if
Python/Kotlin/Dart cannot accept versioned field-decision unions safely.

## 7. Proposed per-rule record schema

The following names and fields are provisional:

```text
RuleOutcomeStateV2 = PASS | FAIL | NOT_APPLICABLE | UNAVAILABLE
RuleRequirementV2 = MANDATORY | OPTIONAL

ConstraintRuleOutcomeV2
  rule_outcome_id: str
  receipt_id: str
  field_id: str
  candidate: CandidateRecordV1
  rule_id: str
  rule_version: str
  requirement: RuleRequirementV2
  state: RuleOutcomeStateV2
  attempted: bool
  evidence_status: ValueAvailabilityStatus
  evidence_references: tuple[str, ...]
  reason_code: RuleReasonCodeV2 | None
  reason_detail: str | None
  exception_code: str | None
  exception_detail: str | None
  theta_a_reference: ConfigurationRefV1
  rule_profile_reference: HardConstraintProfileRefV2
  resource_references: tuple[HardConstraintResourceRefV2, ...]
  record_version: "2"
```

State invariants proposed for approval:

| State | Meaning | Attempt/evidence requirements | Reason/exception requirements |
|---|---|---|---|
| `PASS` | The rule was applicable, evaluated from sufficient evidence, and satisfied. | `attempted=true`; evidence `AVAILABLE`; exact evidence references required. | No failure or exception code. |
| `FAIL` | The rule was applicable, evaluated, and a contradiction was proven. | `attempted=true`; evidence `AVAILABLE`; exact evidence references required. | Typed failure reason required; no exception claim. |
| `NOT_APPLICABLE` | The profile explicitly excludes this rule for the candidate/field or an approved exception applies. It is not a pass. | `attempted=false` applies to the primary hard-rule predicate; evidence `NOT_APPLICABLE`; exclusion source/profile rule required. An applicability or approved-exception check may have inspected runtime evidence before excluding the primary predicate. | Typed exception/applicability code and detail required, including the exact profile clause and any runtime evidence references used to qualify the exception. |
| `UNAVAILABLE` | The rule applies, but required evidence or a required runtime resource cannot establish pass/fail. It is not a failure and not a pass. | Evidence `UNAVAILABLE`; `attempted` records whether absence was detected before or during evaluation; missing evidence/resource references required. | Typed unavailable reason and detail required; no exception claim. |

`OPTIONAL` means audit-only evidence whose absence cannot reject or block the
candidate. It must not be used as a hidden decision-bearing constraint. A rule
that can change eligibility must be `MANDATORY`. Missing optional price evidence
is therefore `OPTIONAL` plus `UNAVAILABLE` (or omitted from the hard-rule profile
and recorded later), never `FAIL`.

For `NOT_APPLICABLE`, `attempted=false` must never be interpreted as "no work was
performed." It states only that the primary pass/fail predicate was not run.
When an approved exception depends on runtime facts, the exception/applicability
check, inspected evidence, resource/profile references, and resulting exclusion
must all be explicit. The result remains `NOT_APPLICABLE`, not an ordinary rule
`PASS`. Exact state, reason, exception, and provenance schemas remain
provisional.

The aggregate proposal is:

```text
ConstraintAggregateStateV2 =
  ELIGIBLE | CONSTRAINT_REJECTED | CONSTRAINT_UNAVAILABLE

ConstraintResultV2
  constraint_result_id: str
  candidate: CandidateRecordV1
  theta_a_reference: ConfigurationRefV1
  rule_profile_reference: HardConstraintProfileRefV2
  ordered_rule_outcomes: tuple[ConstraintRuleOutcomeV2, ...]
  aggregate_state: ConstraintAggregateStateV2
  record_version: "2"
```

`evaluated_rule_ids` should be derived only from `PASS`/`FAIL` outcomes, not used
as a substitute for the complete ordered audit. Aggregate construction must
recompute its state from the complete authenticated profile and outcomes.

## 8. Aggregate truth table

The precedence below is **PROPOSED and PENDING SHARED APPROVAL**. All per-rule
observations remain stored even when a failure determines the aggregate.

| Case | Candidate result | Separate classification | Proposed rationale |
|---|---|---|---|
| All mandatory applicable rules `PASS` | `ELIGIBLE` | Candidate eligibility | The mandatory decision-bearing set completed successfully. |
| One mandatory rule `FAIL` | `CONSTRAINT_REJECTED` | Candidate eligibility | A proven contradiction is sufficient for rejection. |
| Multiple mandatory rules `FAIL` | `CONSTRAINT_REJECTED` | Candidate eligibility | Preserve every failure; do not collapse to one reason. |
| Mandatory `UNAVAILABLE`, no mandatory failure | `CONSTRAINT_UNAVAILABLE` | Legitimate evidence unavailability | Pass/fail cannot be established; scoring is blocked. |
| Mandatory `FAIL` plus mandatory `UNAVAILABLE` | `CONSTRAINT_REJECTED` | Proven rejection with preserved unavailability | Proposed failure precedence; all unavailable observations remain auditable. |
| Optional evidence `UNAVAILABLE`, mandatory rules pass | `ELIGIBLE` | Optional evidence unavailability | Optional absence cannot become negative evidence or block eligibility. |
| Approved exception | Rule `NOT_APPLICABLE`; aggregate from remaining mandatory applicable rules | Applicability | Exception must be profile-backed and auditable; it is not a pass. |
| Every configured rule `NOT_APPLICABLE` | No candidate result; profile/application error | Configuration/profile validity | Fail closed: a candidate must have at least one applicable mandatory rule. Approval needed. |
| No mandatory rule configured | No candidate result; profile invalid | Configuration/profile validity | An audit-only catalogue cannot establish hard eligibility. |
| Contradictory profile definitions | No candidate result; profile invalid | Configuration/profile validity | Contradictory requirement/applicability/resource declarations must fail before evaluation. |
| Required runtime resource unavailable under an otherwise valid profile | `CONSTRAINT_UNAVAILABLE` | Legitimate runtime unavailability | Candidate-specific determination is impossible; no scoring. If the resource is required to make the profile ready at all, classify as profile not ready instead. |
| Invalid or unauthenticated configuration/profile | No candidate result | Configuration/profile invalidity | Do not convert configuration failure into candidate unavailability. |
| Unexpected evaluator exception | No candidate result; `FAILED/PRE_RESOLUTION` | Processing/evaluator failure | Preserve the exception audit; do not manufacture `UNAVAILABLE`. |

The profile must define the expected rule identities and deterministic order per
field/candidate class. Missing, duplicated, extra, or reordered outcomes are
integrity errors, not aggregate outcomes.

## 9. Candidate and `Theta_A` binding

Proposed integrity requirements:

1. Embed the complete immutable `CandidateRecordV1` in every aggregate and
   either embed it or bind by full record equality in each per-rule outcome.
   Matching a candidate ID alone is insufficient.
2. Revalidate `CandidateRecordV1.__post_init__()` at consumption and aggregate
   reconstruction to detect in-memory mutation.
3. Require exact receipt ID, field ID, `c0_candidate_id`, role, value,
   normalized value, provenance, preliminary rank, and limit status equality.
4. Require one exact `ConfigurationRefV1` for `Theta_A` across context,
   operands, profile, all rule outcomes, aggregate, and candidate evidence.
5. A ready `ConfigurationRefV1` is structural metadata only. A nonempty
   `content_hash` does not authenticate manifest bytes.
6. `HardConstraintProfileRefV2` must identify profile ID, version, expected
   ordered rules, applicability definitions, and referenced resource snapshots.
   Its exact canonical hashing/authentication mechanism remains unapproved.
7. Each resource reference must include resource kind, ID, version, and declared
   content reference. Substitution, omission, or version mismatch is an
   integrity/configuration error.
8. Aggregate reconstruction must recompute the rule set, ordering, identity
   bindings, and aggregate state. It must reject post-construction mutation.
9. A complete audit set is measured against the authenticated profile, not
   merely against the records supplied by the caller.
10. Structural equality and revalidation provide contradiction detection, not
    cryptographic authenticity, source-byte proof, or proof that a gate or rule
    executed exactly once.

## 10. Permanent `c0` and Algorithm 4.1 reconciliation

| `c0` / candidate state | Features and scoring | Automatic commit | Proposed controller result | Approval status |
|---|---|---|---|---|
| Eligible `c0` | Allowed when the remaining evidence boundary is valid. | Possible only after probability and `Phi` checks. | Continue Algorithm 4.1. | Thesis-aligned. |
| Proven constraint-rejected `c0` | Bypass; retain full audit and permanent candidate. | Prohibited. | Exact `REVIEW_REQUIRED` versus `FAILED/PRE_RESOLUTION` route is unresolved because lines 9, 17, 21 and the postscript interact. | `PENDING`. |
| `c0` has mandatory constraint `UNAVAILABLE` | Bypass; retain full unavailable audit. | Prohibited. | Must be non-committable; exact review versus failure route is unresolved. Line 16 concerns probability unavailability, not a license to relabel constraint unavailability. | `PENDING`. |
| Altered candidate eligible while `c0` failed | Altered may have evidence, but the required valid-probability comparison to `c0` cannot be satisfied. | Prohibited. | Do not replace `c0`; exact route unresolved. | `PENDING`. |
| Altered candidate rejected; `c0` eligible | Rejected altered candidate bypasses; eligible `c0` continues. | Possible for `c0` only after later checks. | Continue with audited `c0`; preserve altered rejection. | Thesis-aligned. |
| Every retained candidate constraint-unavailable | All bypass. | Prohibited. | Non-committable receipt/field state; exact review versus failure route unresolved. | `PENDING`. |
| Unexpected evaluator failure | No candidate result should be fabricated. | Prohibited. | `FAILED/PRE_RESOLUTION` with processing provenance. | Thesis-aligned category; exact reason enum pending. |

Permanent `c0` remains first in the audit and is never removed, overwritten, or
silently normalized. Algorithm 4.1 line 9's rejected-candidate bypass must apply
to a failed `c0` as an evidence rule, while line 17 prevents selection from
continuing without valid `c0` probability. Line 21/postscript prevents automatic
acceptance but does not unambiguously settle whether actual user review is valid
when the original itself violates a hard rule. That controller policy requires
joint methodology and shared-orchestrator approval.

## 11. `CandidateEvidence` and `FieldDecision` integration

Proposed `CandidateEvidenceV2` changes:

- embed the exact `CandidateRecordV1` and `ConstraintResultV2`;
- add `CONSTRAINT_UNAVAILABLE` to the candidate audit status family;
- preserve `SCORING_ELIGIBLE`, `CONSTRAINT_REJECTED`, and the later,
  independent `REJECTED_PRICE_ONLY` state;
- require both rejected and constraint-unavailable candidates to have no feature
  vector, raw score, or calibrated probability;
- rejected values use `NOT_APPLICABLE` for score/calibration; unavailable hard
  constraints should use `NOT_APPLICABLE` for downstream computation because it
  was deliberately not run, while the cause remains explicitly
  `CONSTRAINT_UNAVAILABLE` in the constraint audit;
- allow seven-slot feature construction only for aggregate `ELIGIBLE`;
- forbid any evidence record for `LIMIT_OVERFLOW` candidates.

The existing `CandidateEvidenceV1` remains compatible only for a deliberate
projection of fully eligible or proven-rejected results. It cannot faithfully
project `CONSTRAINT_UNAVAILABLE`.

Proposed `FieldDecisionV2` responsibilities:

- bind the complete method-ready original, exact configuration bundle, ordered
  retained candidate evidence set, and selected evidence;
- require one audit for every retained candidate and permanent `c0` audit
  presence; an absent required audit is an integrity/completeness failure, not
  `CONSTRAINT_UNAVAILABLE`;
- treat a present audit with `CONSTRAINT_UNAVAILABLE` as legitimate recorded
  unavailability for that candidate, while still prohibiting that candidate
  from feature construction, scoring, selection, or automatic commitment;
- require the selected candidate and permanent `c0` to satisfy all approved
  eligibility, probability, comparison, and policy conditions before automatic
  commitment;
- do not infer a field-wide veto merely because a nonselected retained altered
  candidate has a complete `CONSTRAINT_UNAVAILABLE` audit. Whether that state
  blocks an otherwise valid field commitment is the unresolved controller
  policy in HC-D13;
- retain the current line-16 probability-unavailability safeguard: select exact
  original `c0`, freeze its B2 value, deny automatic commitment, and preserve
  the probability reason;
- represent the separate unresolved constraint-level route only after the
  decision in Section 10 is approved.

`FinalApplicationOutcomeV1` can remain semantically authoritative for frozen
pre-resolution and persistence eligibility, but its concrete
`FieldDecisionV1` type means a coordinated V2 consumer likely needs
`FinalApplicationOutcomeV2` or an approved versioned union. It must preserve the
same prohibition against persistence from fallback, failure, unresolved review,
or any selected/c0 constraint-unavailable state that the approved controller
classifies as non-committable. A nonselected altered candidate's unavailable
audit has no approved field-wide persistence effect until HC-D13 is resolved.

## 12. Reason codes and rule provenance

V1's broad `ConstraintReasonCode` values are insufficient for per-rule state and
unavailability provenance. The following categories are proposed, with exact
enum spelling still `PENDING`:

- failure: `TYPE_OR_PARSE_INVALID`, `SOURCE_OR_PROVENANCE_UNSUPPORTED`,
  `LAYOUT_INCOMPATIBLE`, `ASSOCIATION_AMBIGUOUS`,
  `ARITHMETIC_CONTRADICTION`;
- unavailable: `REQUIRED_OPERAND_UNAVAILABLE`,
  `REQUIRED_RESOURCE_UNAVAILABLE`, `RELATIONSHIP_UNRESOLVED`;
- not applicable: `FIELD_TYPE_NOT_APPLICABLE`,
  `APPROVED_ARITHMETIC_EXCEPTION`, `PROFILE_EXCLUSION`;
- processing/configuration categories must remain outside candidate reason
  codes: `PROFILE_INVALID`, `CONFIGURATION_UNAUTHENTICATED`,
  `EVALUATOR_FAILURE`.

Do not add a generic production `OTHER` escape hatch unless governance defines
how it can be audited. Each rule record must carry rule ID/version, requirement,
profile reference, source evidence references, resource snapshot references,
typed reason/exception, and deterministic position. Human-readable detail
supplements but never replaces typed provenance.

## 13. Migration and serialization approach

Proposed migration, not implementation:

1. Leave Contract V1 source, fixtures, and behavior unchanged.
2. Introduce new `record_version == "2"` records for per-rule outcome,
   constraint aggregate, candidate evidence, and any revised field/final outcome.
3. Reuse V1 immutable value records only where semantics are unchanged; do not
   relabel a V1 `ConstraintResultV1` as V2.
4. Permit a V2-to-V1 projection only under a separately approved, explicit
   mapping contract covering every projected V2 aggregate state, rule state,
   reason code, audit status, and required provenance field. The constructed V1
   record must independently satisfy every V1 constructor invariant.
5. `CONSTRAINT_UNAVAILABLE` has no V1 projection. An unmapped V2 failure reason
   must not be converted automatically to V1 `ConstraintReasonCode.OTHER` to
   conceal semantic loss. If an approved mapping does not exist, projection
   fails closed.
6. Projection must not silently discard profile/resource provenance when the
   receiving workflow requires the complete V2 audit. In that workflow the V2
   record remains authoritative and the legacy V1 view is insufficient.
7. A projection must never turn rejected, unavailable, incomplete, or
   unrepresentable evidence into automatic acceptance or persistence
   eligibility. Consumers must be version-aware and reject unsupported versions
   rather than silently downgrade.
8. Only fully eligible or proven-rejected candidates are potentially
   projectable, and only when their exact state/reason/provenance mapping has
   been approved. Inability to represent any required V2 information safely is
   a closed failure, not permission to omit it.
9. Serialize enum spellings exactly as approved uppercase values. Serialize
   ordered rule/candidate tuples as arrays in profile/c0-first order.
10. Emit declared nullable fields explicitly as JSON `null`; distinguish null
   from empty arrays, absent resources, and `NOT_APPLICABLE`/`UNAVAILABLE` enum
   states. Do not rely on omitted fields for semantic missingness.
11. Preserve finite `Decimal` values as canonical decimal strings. The exact
   scale policy must be part of the approved profile; do not coerce to binary
   floating point.
12. Retain deterministic sorted object keys, compact separators, and UTF-8 text.
   Ordering-sensitive arrays must not be sorted by the serializer.
13. Add language-neutral V2 conformance fixtures only after schema approval,
   covering Python, Kotlin, and Dart parsing, reconstruction, enum failures,
   nulls, Decimal strings, and round-trip bytes.
14. Run all V1 regression/conformance tests unchanged while V2 fixtures are
    additive. Consumers advertise supported versions; no silent downgrade.
15. Keep V1 and V2 in coexistence until Android and both research lanes consume
    V2. Deprecation requires a separately approved date and migration evidence.

Constructor compatibility is intentionally not promised for changed records.
Keyword-only construction or named-field decoding is recommended across
languages to avoid positional breakage.

## 14. Arithmetic and exception dependencies

| Dependency | Decision needed before semantic evaluator coding | Additional held-out/freeze requirement | Existing provisional evidence only |
|---|---|---|---|
| Quantity grammar | Accepted syntax, positivity, units, parse failures, field applicability. | Frozen version and dataset-independent selection record. | B1/B2/B3 parsers. |
| Money grammar | Currency markers, decimal syntax, signs, separators, parse failures. | Frozen currency policy and cross-runtime cases. | B3 money parser. |
| Date grammar | Supported calendar forms, ambiguity/invalid handling, field applicability. | Frozen grammar/version; no test-data tuning. | B1 V1 date behavior. |
| Text grammar | Normalization allowed for type/provenance checks without changing candidate value. | Frozen Unicode/locale policy. | Existing candidate normalization is not automatically a hard rule. |
| Decimal precision/quantum | Internal precision, currency quantum, quantization point. | Frozen manifest and Python/Kotlin/Dart equivalence. | B3 uses `Decimal` and `0.01`. |
| Rounding/tolerance | Rounding mode, inclusive/exclusive boundary, relation-specific tolerance. | Predeclared values and validation-only selection evidence. | B3 uses `ROUND_HALF_UP` and inclusive `0.01`; not adopted here. |
| Weighted units | Recognized units, rate/denominator relationship, conversion policy. | Frozen resource/grammar and representative independent tests. | B3 recognizes selected weight units and avoids conversion. |
| Discounts/promotions/vouchers/taxes | Scope, line versus receipt effects, approved exceptions, sign treatment. | Frozen catalogue and leakage audit. | B3 has generic adjustment/promotion handling. |
| Receipt-total completeness | Which item/adjustment/tax rows must be present before reconciliation is mandatory. | Dataset annotation/completeness protocol. | D3 records raw presence only. |
| Layout/association | One-to-one predicates, ambiguity threshold/grammar, source-span requirements. | Frozen geometry/association profile. | B2 references and D3 identity audit. |
| Mandatory/optional applicability | Rule-to-field matrix, exception precedence, minimum applicable mandatory set. | Authenticated profile and cross-runtime fixture. | Not defined by current shared contracts. |

All first-column policies are blockers for eligibility-bearing semantic evaluator
code. Synthetic record/conformance work may start after schema and truth-table
approval, but held-out execution additionally requires authenticated manifests,
frozen resources, leakage controls, and cross-runtime evidence.

## 15. Cross-team decision/approval register

All IDs are local to this document. Every status is `PENDING`.

| ID | Exact decision question | Verified evidence | Credible options | Provisional recommendation | Consequences / impacts | Owner and required evidence | Blocks synthetic coding? | Blocks held-out evaluation? | Status |
|---|---|---|---|---|---|---|---|---|---|
| HC-D01 | Adopt coordinated V2 or keep V1 plus parallel audit? | V1 has no constraint-unavailable state; Algorithm requires complete audit. | A: coordinated V2; B: parallel boundary and new wrapper. | A. | Shared constructors, fixtures, Android models, both lanes. | Shared-contract owners + Leng/Tai; signed schema review. | Yes | Yes | `PENDING` |
| HC-D02 | Is proven failure dominant over accompanying mandatory unavailability? | A contradiction is known even when another rule cannot complete. | Reject with all observations; or unavailable aggregate. | Proven failure precedence. | Aggregate constructor and reporting metrics. | Methodology owner; written precedence decision. | Yes | Yes | `PENDING` |
| HC-D03 | What happens when every rule is `NOT_APPLICABLE` or no mandatory rule is configured? | No completed mandatory evidence can establish eligibility. | Profile invalid; candidate unavailable; allow eligible. | Profile invalid, fail before evaluation. | Profile validator and fixtures. | Methodology + architecture owners; approved applicability matrix. | Yes | Yes | `PENDING` |
| HC-D04 | How is rejected permanent `c0` routed? | Algorithm lines 9, 17, 21 and postscript do not give one unambiguous controller route. | `REVIEW_REQUIRED`; `FAILED/PRE_RESOLUTION`; new non-committable state. | Preserve audit, prohibit scoring/commit; route undecided. | `FieldDecisionV2`, UI, persistence, evaluation labels. | Methodology owner + shared orchestrator owner; explicit state-transition approval. | No for record-only tests; yes for orchestration | Yes | `PENDING` |
| HC-D05 | How is mandatory-unavailable `c0` routed? | Constraint unavailability is earlier than Algorithm line-16 probability fallback. | Review; failure; explicit non-committable state. | Preserve separately; do not reuse probability fallback without approval. | Decision enums and receipt aggregation. | Same as HC-D04. | No for record-only tests; yes for orchestration | Yes | `PENDING` |
| HC-D06 | What exact rule catalogue and field applicability matrix are mandatory? | Thesis gives categories, not complete executable rules. | Small universal set; field-specific sets; hybrid profile. | Versioned field-specific profile with universal provenance checks. | Evaluator semantics and complete-audit validation. | Leng methodology owner with Tai extraction review; approved catalogue. | Yes for semantic evaluator | Yes | `PENDING` |
| HC-D07 | Which arithmetic grammar, quantum, rounding, tolerance, and exception rules apply? | B3 values are provisional comparator policy only. | Adopt B3 after review; define proposed-specific policy; share a frozen kernel. | Review shared-kernel reuse, without automatic adoption. | Numeric results and B3/proposed comparability. | Leng/Tai + methodology owner; policy manifest and validation evidence. | Yes for arithmetic rules | Yes | `PENDING` |
| HC-D08 | How are profile and resource bytes authenticated? | `ConfigurationRefV1.content_hash` is structurally checked but not authenticated. | Signed manifest; trusted release checksum; deployment registry. | Trusted versioned manifest plus independently verified digest; exact mechanism pending. | Integrity boundary, Android packaging, reproducibility. | Architecture/security/shared owners; threat model and cross-runtime digest fixture. | No for synthetic structural tests | Yes | `PENDING` |
| HC-D09 | Are optional rules audit-only, and can an optional failure affect eligibility? | Optional missing price must not block or become negative evidence. | Audit-only optional; optional-but-rejecting; omit from hard profile. | Optional is audit-only; decision-bearing means mandatory. | Aggregate truth table and metrics. | Methodology owner; written semantics. | Yes | Yes | `PENDING` |
| HC-D10 | Which downstream records receive V2 versions? | `CandidateEvidenceV1` and `FinalApplicationOutcomeV1` use concrete V1 types. | V2 all changed records; versioned union; adapter wrapper. | V2 constraint/evidence/decision, with final outcome revised only if required by language models. | API churn and migration scope. | Shared-contract + Android owners; type-system prototype and schema review. | Yes for downstream fixtures | Yes | `PENDING` |
| HC-D11 | What are exact enum spellings, null semantics, array order, and Decimal canonical form? | V1 conventions exist; new states/records do not. | Extend V1 conventions; new envelope schema. | Extend V1 deterministic conventions additively. | Python/Kotlin/Dart byte-level conformance. | Shared-contract owners; approved JSON schema and three-runtime fixture. | Yes for conformance coding | Yes | `PENDING` |
| HC-D12 | Can a required runtime resource be candidate-unavailable versus profile-not-ready? | Resource absence may be per-candidate or global. | Always profile error; always candidate unavailable; distinguish by declared load scope. | Distinguish: global required resource blocks profile, candidate-specific missing lookup yields unavailable. | Evaluator error taxonomy and retries. | Methodology + architecture owners; resource lifecycle specification. | Yes | Yes | `PENDING` |
| HC-D13 | Does constraint unavailability for a nonselected retained altered candidate block automatic field commitment when `c0` and the otherwise selected candidate satisfy all required conditions? | Candidate completeness requires an audit for every retained candidate, but candidate-local `CONSTRAINT_UNAVAILABLE` does not by itself establish a contradiction in another eligible candidate. | A: any retained altered unavailability vetoes field commitment; B: only selected/`c0` or explicitly policy-required candidate unavailability vetoes, while the nonselected audit remains recorded. | None; both options remain open pending methodology/orchestrator approval. | A is more conservative but may force review for irrelevant alternatives; B permits commitment from complete eligible evidence but requires an explicit completeness and selection policy. Affects `FieldDecisionV2`, receipt aggregation, UI reasons, evaluation accounting, and persistence eligibility. | Leng methodology owner + shared orchestrator owner; written controller truth table and adversarial decision fixtures. | Yes for field-decision/orchestrator coding; no for candidate-audit record tests | Yes | `PENDING` |

Practical coordination sequence:

1. Leng, as method owner, approves rule states, precedence, applicability, `c0`
   routing, and arithmetic/exception policy.
2. Tai reviews extraction evidence availability, association semantics, and B3
   comparability without transferring ownership of the proposed method.
3. Shared-contract and Android owners approve versioned records, serialization,
   and migration.
4. An architecture/integrity audit verifies complete binding, configuration
   trust boundaries, and orchestrator state transitions.
5. Only then may a separately authorized task add synthetic contract records and
   conformance fixtures; semantic evaluation and held-out use require later,
   separate authorization.

## 16. Proposed adversarial conformance matrix

These are future synthetic tests only; none is implemented by this task.

| Test input | Invariant | Expected result |
|---|---|---|
| One valid `PASS` mandatory rule | Applicable evaluated evidence can pass. | Candidate aggregate `ELIGIBLE`. |
| One valid `FAIL` mandatory rule | Proven contradiction cannot score. | `CONSTRAINT_REJECTED`; typed reason retained; features/scores/probability absent. |
| Valid `NOT_APPLICABLE` with approved exception | Exclusion is not pass/fail. | Rule retained as N/A; aggregate derives from remaining mandatory rules. |
| Mandatory rule `UNAVAILABLE` | Missing evidence is not failure. | `CONSTRAINT_UNAVAILABLE`; no scoring. |
| Required retained-candidate audit omitted | Absence is not legitimate unavailability. | Integrity/completeness rejection; no field decision. |
| Present nonselected altered candidate audit is unavailable while `c0` and selection are otherwise valid | Candidate-local unavailability must not silently become a field-wide veto or silently be ignored. | Preserve the audit and exercise the approved HC-D13 controller branch; until approval, no conformance expectation may claim either automatic commit or mandatory review. |
| Optional price lookup unavailable | Missing price is not negative evidence. | Optional unavailable audit; candidate remains eligible if mandatory rules pass. |
| One failure plus one unavailable mandatory rule | Failure precedence must not erase other observations. | Rejected aggregate with both full rule records. |
| Multiple failures | No first-failure information loss. | Rejected aggregate retains all deterministic failures. |
| Every rule N/A | Minimum mandatory applicability is enforced. | Profile/application integrity error; no candidate result. |
| No mandatory rule in profile | Audit-only profile cannot assert hard eligibility. | Profile invalid before evaluation. |
| Contradictory profile definitions | Profile cannot be interpreted deterministically. | Configuration/profile error; no candidate result. |
| Globally required resource absent | Not a candidate observation. | Profile not ready/invalid; no evaluation. |
| Candidate-specific required lookup absent | Legitimate runtime evidence gap. | Candidate constraint unavailable. |
| Unexpected evaluator exception | Exceptions cannot masquerade as evidence. | `FAILED/PRE_RESOLUTION`; no synthetic candidate result. |
| Rejected `c0` | Permanent original is not deletable or scoreable. | `c0` audit retained first; no feature/score/calibration; no auto-commit. |
| Unavailable `c0` | Unknown hard state is not eligible. | `c0` retained; no scoring or auto-commit; unresolved controller route exposed. |
| Eligible altered with failed `c0` | Altered cannot bypass required c0 comparison. | No automatic replacement; unresolved controller route exposed. |
| Rejected altered with eligible `c0` | One rejected alternative must not block valid original. | Altered bypassed; c0 can continue to later checks. |
| All retained candidates unavailable | No candidate is silently promoted. | All audits retained; no scoring/commit. |
| Overflow candidate supplied to evaluator | Limit boundary is strict. | Integrity rejection before rule evaluation. |
| Same candidate ID, altered value/provenance/rank | ID alone is insufficient. | Reconstruction/integrity rejection. |
| Wrong receipt/field/`c0` identity | Cross-field substitution is forbidden. | Integrity rejection. |
| Missing, duplicate, extra, or reordered rule record | Complete profile-defined audit is required. | Aggregate reconstruction rejection. |
| Wrong rule/profile version | Outcome must bind exact policy. | Configuration/integrity rejection. |
| Wrong `Theta_A` reference | Constraint policy cannot be relabelled. | Integrity rejection. |
| Substituted resource snapshot | Runtime evidence provenance is immutable. | Integrity/configuration rejection. |
| Nonempty but unauthenticated hash | Structural presence is not authenticity. | Held-out execution blocked; no authenticity claim. |
| Mutated frozen config/candidate/outcome via `object.__setattr__` | Consumption revalidates stored records. | Public API and aggregate reconstruction reject. |
| Rejected/unavailable candidate with a feature or score | No downstream leakage after bypass. | Constructor rejection. |
| Constraint-unavailable evidence marked scoring-eligible | Unknown cannot become pass by default. | Constructor rejection. |
| Auto-accepted decision selecting rejected/unavailable evidence | Automatic commitment needs eligibility and probability. | Constructor rejection. |
| Price-only status applied before hard eligibility | Price policy is a later separate boundary. | Constructor/order rejection. |
| Deterministic JSON repeated twice | Same immutable graph has stable encoding. | Byte-identical UTF-8 JSON. |
| JSON null omitted or changed to empty value | Missingness semantics are explicit. | Cross-runtime conformance rejection. |
| Python/Kotlin/Dart round trip | Shared values and ordering survive runtimes. | Equal reconstructed records and canonical fixture output. |

## 17. Synthetic coding versus held-out freeze prerequisites

Synthetic record/conformance coding requires prior approval of:

- HC-D01, HC-D02, HC-D03, HC-D09, HC-D10, and HC-D11;
- the provisional per-rule and aggregate schemas;
- exact enum spellings and constructor invariants;
- the distinction between structural validation and authentication.

Synthetic semantic evaluator coding additionally requires HC-D06, HC-D07, and
HC-D12. Receipt/field orchestration requires HC-D04, HC-D05, and HC-D13.
Candidate-audit record tests may cover a present nonselected unavailable audit
without resolving HC-D13, but field-decision tests must not assert a field-wide
commit/review result until that policy is approved.

Held-out execution requires all above decisions plus:

- authenticated and validation-frozen `Theta_A` hard-rule profile;
- frozen grammar, tolerance, rounding, exception, and resource manifests;
- independent dataset split/leakage controls;
- approved resource provenance and licensing;
- Python/Kotlin/Dart conformance evidence;
- an architecture audit demonstrating no hidden ground truth, no test-set
  tuning, and no automatic commit from rejected/unavailable evidence.

No dataset, OCR, B2/B3 execution, scoring, calibration, or held-out evaluation
was performed for this document.

## 18. Open blockers

1. Contract architecture and downstream versioning are not shared-approved.
2. The complete hard-rule catalogue and applicability matrix do not exist as an
   approved profile.
3. Exact quantity, money, date, text, arithmetic, weighted-item, adjustment,
   promotion, voucher, tax, and receipt-completeness policies are unresolved.
4. Proven-failure precedence and zero-applicable-rule behavior are proposals.
5. Rejected or mandatory-unavailable permanent `c0` has no approved controller
   route reconciling Algorithm 4.1 lines 9, 17, and 21.
6. The field-wide effect of a nonselected altered candidate's complete
   `CONSTRAINT_UNAVAILABLE` audit is unresolved (HC-D13).
7. `Theta_A` and resource manifest authentication are not implemented.
8. Cross-runtime V2 schema and conformance fixtures are not approved.
9. No eligibility-bearing evaluator, V2 constructor, Android consumer, or
   persistence integration is authorized.

## 19. Exact approvals requested

The next review should explicitly approve, reject, or amend:

1. Option A as the shared direction (HC-D01).
2. The four per-rule states and their exact attempted/evidence invariants.
3. The three aggregate states and truth-table precedence (HC-D02, HC-D03,
   HC-D09, HC-D12).
4. Full immutable candidate, `Theta_A`, profile, and resource binding.
5. V2 downstream scope and V1 coexistence/migration (HC-D10).
6. Safe V2-to-V1 state/reason/provenance mappings, fail-closed projection, and
   serialization/null/Decimal/order conventions (HC-D11).
7. The exact `c0` routes for rejected and unavailable constraints (HC-D04,
   HC-D05).
8. Whether a nonselected altered candidate's constraint unavailability blocks
   otherwise valid automatic field commitment (HC-D13).
9. The rule catalogue, field applicability, arithmetic, and exception policies
   before any semantic implementation (HC-D06, HC-D07).
10. The authentication and held-out freeze process (HC-D08).
11. A separately scoped implementation task limited first to immutable V2
    records and synthetic conformance tests, with no semantic evaluator.

Silence, review comments, or approval of this prose alone must not be interpreted
as authorization to implement or to use held-out data.

## 20. Final Git status

Post-authoring verification is recorded as follows:

- expected branch: `feature/self-correction`;
- expected HEAD and remote-tracking HEAD:
  `a6545373f8e9059f7c5adea9dce3e0a3b038e1e9`;
- frozen foundation: `36e6cef` remains an ancestor;
- staged files: none;
- tracked modifications: none;
- sole untracked file:
  `docs/proposed_hard_constraint_contract_change_v2.md`;
- no staging, commit, push, pull, merge, reset, or branch switch performed.

This status must be confirmed by the final verification commands before the
proposal is returned for independent design audit.
