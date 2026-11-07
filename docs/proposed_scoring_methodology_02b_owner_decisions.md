# SCORING-METHODOLOGY-02B Owner Decision Record

## 1. Identity and purpose

This document records `SCORING-METHODOLOGY-02B` under the bounded
documentation authorization `SCORING-02B-DOC-01`.

- Proposed-method methodology owner: Leng Wei Heng.
- Shared-interface and cross-runtime owner: Tai Yong Xin.
- Previous milestone: `SCORING-METHODOLOGY-02A`, a read-only design review.
- Previous documentary baseline: the closed `SCORING-METHODOLOGY-01C`
  reconciliation.
- Current research state: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`.

The purpose of 02B is to reconcile the design directions selected by both
owners for future V2-native scoring evidence and trusted `Theta_A` resolution.
It does not freeze a public record schema, wire format, trusted manifest,
resolver implementation, scorer, calibration method, controller policy or
evaluation procedure. Direction-level owner alignment is not exact-contract
approval and is not implementation authorization.

## 2. Evidence register

### 2.1 Verified repository evidence

The repository was verified at `main` commit
`3236b4a392ec42c4e9a8ed2235b0313e634721e1` with no staged, tracked or
untracked changes before this document was created.

| Source | Verification and role |
|---|---|
| `docs/proposed_scoring_methodology_01c_reconciliation.md` | Committed 01C baseline. Binary-safe Git-blob SHA-256: `6129A90C7AC64A711F8194B4F087A8E4881E39D2CA577893AC3C46AF8A62FE57`. It preserves the SM-01–SM-11 statuses, label/leakage safeguards and permanent-c0 restrictions used here. |
| `docs/proposed_method_traceability_v0.md` | Repository traceability for Algorithm 4.1, price-only rejection before scoring, raw-score/calibration separation, and distinct `Theta_A`, `Kappa` and `Phi` responsibilities. |
| `docs/proposed_feature_construction_v0.md` | Repository description of complete V2 audit preservation, seven-slot eligible vectors, explicit missingness, atomic validation and the prohibition on unsafe V2-to-V1 projection. |
| `docs/proposed_hard_constraint_contracts_v2.md` | Repository description of permanent c0, complete candidate audit states, source binding, ordering and declared-hash limitations. |
| `docs/proposed_hard_constraint_contract_change_v2.md` | Repository record showing HC-D04, HC-D05 and HC-D13 remain unresolved and declared hashes do not authenticate source bytes. |
| `docs/proposed_method_decision_log.md` | Repository decision evidence preserving c0, `Theta_A` source binding and the exclusions on selection, commitment, controller and persistence behavior. |
| `pipeline/proposed/contracts.py` | Current V1 implementation evidence. It distinguishes configuration references but does not provide a trusted scorer resolver or a safe V2-native score-audit schema. |
| `pipeline/proposed/feature_construction.py` | Current implementation evidence for source-bound, ordered, atomic feature construction. It does not implement scoring, calibration, selection or a public cross-runtime score schema. |

Repository implementation is evidence of the current engineering boundary. It
does not by itself approve future methodology or authenticate a future scorer.

### 2.2 Verified local Codex evidence

The original completed 02A assistant report was recovered from the local Codex
session archive:

- Session file:
  `C:\Users\Marcus\.codex\sessions\2026\10\13\rollout-2026-10-13T20-50-25-01a13550-6d7e-76a0-94e2-04fbd87124c2.jsonl`.
- Response ordinal: `19813` (physical line `19814`).
- Recorded timestamp: `2026-11-05T18:28:44.476Z`.
- Extracted UTF-8 report SHA-256:
  `D1D6A1744A1756A8C2FAEF7D43C856A633E8BCDBAC17119D4379E6BA85787B37`.

The separate 02A task prompt is available at
`C:\Users\Marcus\.codex\attachments\b3dbaca9-2954-49a4-a268-bef84a8ed9dd\Pasted text.txt`
with raw SHA-256
`940273B9308E35B7FE7CF534785D6F2067DFCBB36E57B0868A7DDAAEB5C02542`.
The prompt is an instruction, not the completed review.

The recovered 02A report found that a V2-native scoring audit was structurally
feasible but that SM-01 and SM-06 were not approval-ready. It provisionally
preferred one ordered audit entry per retained candidate; separated
hard-constraint eligibility from price-only-support admission; recommended an
initially empty candidate-local score-unavailability catalogue; placed
configuration, integrity, compatibility and unexpected execution failures at
an atomic field boundary; and proposed a governed parent `Theta_A` manifest
plus a separately versioned `READY`/`NOT_READY`/`NOT_VALID` resolver. It also
left the zero-admitted-candidate path as an explicit owner decision. Those were
recommendations, not approvals.

This local session evidence verifies what the prior Codex report said. It is
not an externally authenticated owner signature.

### 2.3 Supplied owner statements and limitations

The creation authorization and the L1–L7/T1–T7 selections are supplied in the
owner conversation at
`C:\Users\Marcus\.codex\attachments\5bcfe663-9954-40b4-a14a-acad27e9d75a\Pasted text.txt`,
raw SHA-256
`4C59DF4D2605CDCDEBFEFD04D18F240F7F55D4995DC750840822F129471AC1F2`.

This supplied evidence states:

- Leng selected L1–L7 = A, including explicit confirmation of L4 = A.
- Tai selected T1–T7 = A with all recorded conditions.

No separate primary Tai approval attachment, external signature, message ID or
independently authenticated timestamp was recovered. Tai's selections are
therefore recorded as supplied conversational owner evidence. This limitation
does not change the selections recorded below, but it prevents a claim of
external authentication.

All explanatory text in this document that is not a direct owner selection is
a reconciliation or interpretation grounded in the sources above. It must not
be treated as a new owner decision.

## 3. Leng L1–L7 confirmed decisions

### L1 = A — Complete retained-candidate scoring audit

**Confirmed direction:** A future field audit contains one scoring-audit entry
for every retained V2 candidate, including candidates whose scoring state is
`NOT_APPLICABLE`.

**Conditions:** Permanent c0, exact D3 ordering, complete V2 states and exact
source binding remain intact. `CONSTRAINT_REJECTED` and
`CONSTRAINT_UNAVAILABLE` cannot be collapsed through an unsafe V2-to-V1
projection.

**Still pending:** Exact record names, fields, identifiers, versions,
serialization and reconstruction invariants require shared-contract approval.

### L2 = A — Separate typed pre-score admission

**Confirmed direction:** Pre-score admission is recorded independently from the
original V2 hard-constraint result.

**Conditions:** A price-only-support rejection must not rewrite a V2 candidate
from `ELIGIBLE` to another hard-constraint state. The separate admission record
must preserve the original V2 result and source evidence.

**Still pending:** The admission vocabulary, scope, reason catalogue and public
wire representation require joint approval.

### L3 = A — No candidate-local score `UNAVAILABLE` reasons initially

**Confirmed direction:** The initial permitted candidate-local score-
unavailability catalogue is empty.

**Conditions:** Future candidate-local reasons require explicit approval of a
closed catalogue. Configuration, manifest, integrity, compatibility and
unexpected execution failures must not be relabelled as candidate-local
unavailability.

**Still pending:** Any future catalogue and its versioning require methodology
and shared-contract approval.

### L4 = A — Zero-admitted-candidate audit-only bypass

**Confirmed direction:** When zero candidates are admitted to scoring, a
complete audit-only result may be produced without invoking the trusted scorer
resolver. This decision is no longer provisional at the design-direction level.

**Conditions:** Every retained candidate and its source audit remain present.
The bypass must record non-invocation and must not manufacture a scorer
`READY` result, raw score, probability, selection or replacement. Malformed or
incomplete source evidence still fails validation.

**Still pending:** The exact bypass record, status and constructor invariants
require shared-contract review.

### L5 = A — Exact source binding and atomicity

**Confirmed direction:** Future scoring evidence requires complete retained-
candidate auditability, exact D3/V2 relationships and exact binding to every
eligible feature vector.

**Conditions:** A configuration or scoring failure cannot yield a partial
successful field aggregate. Raw scoring evidence remains separate from later
calibration evidence.

**Still pending:** Public field definitions, runtime identity checks, serialized
content-equality checks and atomic failure types require approval.

### L6 = A — Trusted parent `Theta_A` manifest

**Confirmed direction:** Trust is rooted in a governed parent `Theta_A`
manifest that pins the scorer component and dependent artifacts.

**Conditions:** The existing synthetic `Theta_A` reference cannot be repurposed
as approval or authentication for a learned scorer. Equal identifiers and
self-declared hashes remain metadata, not proof of approved artifact bytes.

**Still pending:** Manifest schema, canonical digest preimage, approval registry,
trust root, distribution, revocation and offline verification.

### L7 = A — Separate trusted resolver and atomic failure boundary

**Confirmed direction:** A separately versioned resolver outcome distinguishes
`READY`, `NOT_READY` and `NOT_VALID`.

**Conditions:** Trusted resolver readiness is distinct from legacy
`ConfigurationState.READY`. The resolver must verify approved provenance,
manifest relationships and the artifact bytes actually executed.
Configuration, integrity, compatibility and unexpected execution failures are
field-level failures. `READY` establishes structural trust and compatibility;
it does not establish statistical validity.

**Still pending:** Exact resolver result schema, reasons, retryability,
trust-store interface and time-of-check/time-of-use controls.

## 4. Tai T1–T7 confirmed decisions

### T1 = A — Complete V2 scoring evidence

**Confirmed direction:** One scoring-audit entry is retained for every V2
candidate, including bypassed candidates.

**Conditions:** Exact D3 ordering, permanent c0, original constraint outcomes
and complete traceability are preserved.

**Still pending:** The exact shared schema and cross-runtime constructor rules.

### T2 = A — Separate pre-score admission evidence

**Confirmed direction:** Explicit typed pre-score admission evidence is separate
from hard-constraint eligibility.

**Conditions:** Price-only-support rejection cannot be represented by modifying
the V2 outcome.

**Still pending:** Vocabulary and scope require joint approval.

### T3 = A — Cross-runtime serialization

**Confirmed direction:** A future public scoring schema is explicit, versioned
and shared across Python and Kotlin.

**Conditions:** It preserves strict required keys, closed enums, explicit nulls,
c0-first ordering, canonical finite Decimal strings, duplicate-key rejection
and unsupported-version rejection. Synthetic cross-runtime conformance fixtures
are required before implementation acceptance.

**Still pending:** Exact IDs, wire fields, Decimal grammar, serialization
details, fixture manifest and consumer APIs.

### T4 = A — Trusted `Theta_A` distribution and authentication

**Confirmed direction:** Independently governed pinned trust evidence covers the
approved parent `Theta_A` manifest and its dependent artifacts.

**Conditions:** Future policy addresses version pinning, supersession,
revocation and offline verification. Self-declared hashes and equal IDs are not
sufficient authenticity evidence. This document does not claim that a trust
infrastructure already exists.

**Still pending:** Trust-root ownership, registry format, signed or otherwise
governed distribution, update procedure and offline failure behavior.

### T5 = A — Distinct resolver and scoring failures

**Confirmed direction:** The design keeps distinct:

- candidate `NOT_APPLICABLE`;
- any future separately approved candidate-local `UNAVAILABLE`;
- scorer `NOT_READY`;
- scorer `NOT_VALID`; and
- atomic field-level integrity, compatibility or unexpected execution failure.

**Conditions:** Initially no candidate-local `UNAVAILABLE` reason is permitted.
Legacy configuration `READY` does not imply trusted scorer `READY`.

**Still pending:** Closed reason catalogues and public failure/result schemas.

### T6 = A — Audit-only bypass

**Confirmed direction:** When no candidate is admitted, the system preserves a
complete audit-only result without invoking the trusted scorer. Leng's matching
L4 = A is explicitly confirmed, so this pair is no longer provisional at the
design-direction level.

**Conditions:** Source evidence remains complete and non-invocation is recorded.
Malformed source audits fail. The bypass cannot imply readiness or enable
automatic replacement.

**Still pending:** Exact bypass/result shape and cross-runtime conformance.

### T7 = A — Controller and evaluation exclusions

**Confirmed direction:** Permanent c0 and the prohibition on automatically
replacing an ineligible c0 remain in force.

**Conditions:** HC-D04, HC-D05 and HC-D13 remain unresolved. `Kappa` and `Phi`
remain separate from `Theta_A`. Synthetic conformance cannot establish scorer
effectiveness.

**Still pending and unauthorized:** Trained scoring, Android runtime activation,
controller integration, real-receipt work and held-out evaluation.

## 5. Joint reconciliation matrix

| Leng direction | Tai direction | Design-direction reconciliation | Exact-contract status |
|---|---|---|---|
| L1 | T1 | Aligned on one complete ordered audit entry per retained candidate, including bypassed and `NOT_APPLICABLE` candidates. | Pending. |
| L2 | T2 | Aligned on a typed pre-score admission boundary separate from hard constraints and on preserving price-only rejection outside V2 eligibility. | Vocabulary and schema pending. |
| L3 and L7 | T5 | Aligned on an initially empty candidate-local unavailability catalogue and distinct resolver/atomic failure states. | Reason and result schemas pending. |
| L4 | T6 | Aligned on a complete zero-admitted audit-only bypass with no resolver invocation and no inferred readiness. L4/T6 are no longer provisional. | Bypass record pending. |
| L5 | T1 and T5 | Aligned on exact source relationships, complete population audit and atomic field failure. | Constructor and serialization rules pending. |
| L6 | T4 | Aligned on a governed parent `Theta_A` manifest, pinned dependencies and an independent trust root. | Trust architecture pending. |
| Leng's source/audit requirements | T3 | Aligned on an explicit strict cross-runtime schema and conformance fixtures. | Wire schema pending. |
| All Leng restrictions | T7 | Aligned on permanent c0, separated `Kappa`/`Phi`, unresolved controller policy and no evaluation or runtime activation. | Controller/evaluation decisions remain unresolved or deferred. |

All fourteen owner selections are aligned at the design-direction level. This
matrix does not approve exact public contracts, record names, serialization,
resolver code or scorer execution.

## 6. Agreed scoring-state principles

The future design must distinguish the following states without collapsing one
into another:

| State | Required treatment |
|---|---|
| 1. Hard-constraint eligible and score-admitted | An eligible feature vector may enter scoring only after trusted resolver readiness. A future available score must be finite raw evidence, not a probability. |
| 2. Hard-constraint eligible but rejected at pre-score admission | Preserve the V2 `ELIGIBLE` result and record a separate typed admission rejection, including price-only support where applicable. Do not score. |
| 3. `CONSTRAINT_REJECTED` | Preserve the complete V2 rejection audit. Scoring is `NOT_APPLICABLE`; no feature or score is fabricated. |
| 4. `CONSTRAINT_UNAVAILABLE` | Preserve the complete V2 unavailable audit. Scoring is `NOT_APPLICABLE`; it is not silently converted to rejection or eligibility. |
| 5. Zero score-admitted candidates | Produce the approved complete audit-only bypass, record resolver non-invocation and produce no readiness, score, probability, selection or replacement. |
| 6. Trusted scorer `NOT_READY` | Treat as a field-level missing-prerequisite outcome, not candidate-local `UNAVAILABLE`. No partial successful field aggregate is returned. |
| 7. Trusted scorer `NOT_VALID` | Treat as a field-level failed-validation outcome, not candidate-local `UNAVAILABLE`. No partial successful field aggregate is returned. |
| 8. Atomic integrity, configuration or unexpected execution failure | Fail the field scoring operation atomically. Do not return partial candidate success or conceal the failure as ordinary candidate missingness. |

Hard-constraint eligibility and price-only-support admission are distinct by
owner decision. The initial candidate-local score-`UNAVAILABLE` catalogue is
empty. This documentary description does not create a new implementation enum,
record or reason taxonomy.

## 7. Trusted `Theta_A` design principles

The owners align on these future trust principles:

1. A governed parent `Theta_A` manifest identifies and pins its scorer
   component, feature contract, dependencies and relevant runtime constraints.
2. Expected trust evidence originates from an independent governed trust root,
   not solely from the caller-supplied manifest.
3. Canonical manifest encoding, digest algorithm and digest preimage remain to
   be approved.
4. Resolution verifies artifact format, dependency/runtime compatibility,
   feature schema, slot ordering, missingness treatment, numeric settings and
   the relationship to the upstream `Theta_A` configuration.
5. The bytes actually executed must be the bytes that were verified. Equal IDs,
   versions or declared hashes do not establish that fact.
6. The resolver is separately versioned and reports `READY`, `NOT_READY` or
   `NOT_VALID` with a future closed reason taxonomy.
7. Offline trust, registry snapshots, update policy, supersession, revocation
   and conflicting approvals remain open design questions.
8. `Kappa` calibration and `Phi` selective-verification policy remain separate
   configurations and cannot be absorbed into scorer readiness.
9. Structural `READY` means trusted material is approved and compatible for
   raw scoring. It does not prove empirical usefulness, correctness,
   calibration, generalization or evaluation freeze.

No real scorer, manifest, artifact, dependency set or runtime is marked
`READY` by this document.

## 8. Preserved SM-01–SM-11 registry

The 01C statuses are preserved exactly:

| Decision | Status |
|---|---|
| SM-01 | PROPOSED |
| SM-02 | DEFER |
| SM-03 | PROPOSED |
| SM-04 | DEFER |
| SM-05 | PROPOSED |
| SM-06 | BLOCKED |
| SM-07 | BLOCKED |
| SM-08 | DEFER |
| SM-09 | UNRESOLVED |
| SM-10 | DEFER |
| SM-11 | UNRESOLVED |

`ALIGNED` in this document describes owner agreement on a design direction. It
does not replace any status above. In particular, SM-01 is not `APPROVED` and
SM-06 is not `READY` or unblocked.

### SM-07 safeguards retained

- Correctness references remain governed and distinguish `CORRECT`,
  `INCORRECT` and `INDETERMINATE`; missing reference evidence is not silently
  relabelled as an incorrect candidate.
- Training, validation, threshold selection and held-out evaluation remain
  partitioned by approved groups to prevent receipt/source leakage.
- Held-out data cannot influence feature, scorer, calibration, threshold or
  policy decisions.
- Data access, label adjudication, sample sufficiency and empirical work require
  separate authorization and governance.

### SM-09 safeguards retained

- Permanent c0 remains the no-scoring reference and cannot be rewritten by an
  altered candidate or later score record.
- An ineligible c0 prohibits automatic replacement. Review, failure or a future
  approved noncommittable state remain possible directions, not current
  implementation outcomes.
- No artificial vector, raw score or calibrated probability may be created for
  an ineligible c0.
- HC-D04, HC-D05 and HC-D13 remain unresolved and require an explicit
  controller truth table before commitment behavior can be approved.

## 9. Unresolved detailed design decisions

| Pending requirement | Proposed responsibility | Required approval or evidence |
|---|---|---|
| Exact V2 candidate scoring record schema | Leng methodology lead; joint shared-contract approval with Tai | Field list, versions, nullability, closed enums and independent review. |
| Exact field-level audit schema | Leng methodology lead; Tai cross-runtime review; joint approval | Complete population invariants, atomicity and consumer requirements. |
| Deterministic record identity | Joint | Canonical ID inputs, collision behavior and serialization stability. |
| Source-bound reconstruction rules | Leng backend lead; joint review | Live identity versus immutable content checks, no provenance-authentication overclaim. |
| Pre-score admission vocabulary and scope | Leng methodology lead; joint approval | Price-only treatment, applicability, closed reasons and field scope. |
| Zero-admitted bypass result shape | Joint | Explicit non-invocation semantics, complete audit invariants and wire fixtures. |
| Candidate score-status reason catalogue | Leng methodology lead; joint approval if public | Initially empty; any addition needs closed reason semantics and failure-boundary review. |
| Raw Decimal grammar, precision and tie behavior | Leng methodology plus Tai cross-runtime review; joint approval | Canonical finite syntax, scale/exponent/signed-zero rules, arithmetic precision and tie tests. |
| Strict Python/Kotlin wire serialization | Tai/shared-interface lead; joint approval | Required keys, duplicate handling, unknown versions/enums, explicit nulls and conformance fixtures. |
| Trusted manifest fields and canonical encoding | Joint architecture; Leng owns scorer semantics and Tai owns distribution compatibility | Manifest schema, canonical bytes, digest preimage, dependency representation and review. |
| Parent `Theta_A` trust root and approval registry | Joint architecture/governance | Independent pinned trust evidence, authority model and authenticated distribution. |
| Offline versioning, revocation and supersession | Joint architecture/governance with Tai distribution review | Registry snapshots, rollback/conflict policy and offline failure behavior. |
| Resolver reason taxonomy | Leng backend lead; joint shared-contract review | Closed `NOT_READY`/`NOT_VALID` reasons, retryability and no candidate-local leakage. |
| Runtime and artifact verification | Leng backend and Tai compatibility owners; joint review | Artifact-byte verification, dependency/runtime checks and time-of-check/time-of-use protection. |
| Independent shared-contract review | Joint owners | Review of exact schemas, fixtures, failure precedence and compatibility before coding. |
| Future scoring feasibility and governed data evidence | Leng methodology with Tai evaluation/data infrastructure under joint governance | Approved labels, grouped leakage controls, sufficient evidence and separate empirical authorization. |

These assignments are proposed responsibility boundaries, not signatures or
implementation delegation. Exact contracts remain prerequisites to coding.

## 10. Explicit prohibitions

This record does not authorize:

- scorer family selection, scorer implementation or artifact packaging;
- model training, fitting or hyperparameter selection;
- calibration, `Kappa` fitting or probability production;
- automatic candidate selection, replacement or correction commitment;
- controller, orchestration, persistence or inventory integration;
- Android or other runtime integration;
- modification of Contract V0, Contract V1, Contract V2, D3, G2A, permanent c0
  or existing `Theta_A` source binding;
- real-receipt, reference, validation or held-out evaluation work;
- research or evaluation freeze; or
- Git integration of this document without separate authorization.

No scoring or evaluation test, trained parameter, threshold, manifest digest or
empirical result is created or approved here.

## 11. Closure classification

`SCORING_02B_OWNER_DIRECTIONS_ALIGNED`

`SCORING_02B_DOCUMENT_CREATED_PENDING_INDEPENDENT_REVIEW`

`SM_01_EXACT_CONTRACT_PENDING_APPROVAL`

`SM_06_TRUSTED_RESOLVER_PENDING_APPROVAL`

`SCORING_METHODOLOGY_NOT_FROZEN`

`SCORING_IMPLEMENTATION_NOT_AUTHORIZED`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
