# SCORING-METHODOLOGY-01C: Owner-direction reconciliation

## 1. Document identity and purpose

- Record identity: `SCORING-METHODOLOGY-01C`
- Creation milestone: `SCORING-01C-DOC-CREATION-01`
- Creation scope: documentation only
- Research state: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

This document reconciles the original `SCORING-METHODOLOGY-01B — Owner
decision package` with the methodology directions communicated by Leng Wei
Heng and Tai Yong Xin. All eleven owner directions are recorded as aligned
with the original 01B recommendation and status.

Alignment does not resolve a deferred, blocked, or unresolved technical
decision. This document neither freezes the scoring methodology nor authorizes
implementation, model fitting, calibration, candidate replacement, controller
integration, data access, or evaluation.

## 2. Source evidence register

### 2.1 Authoritative 01B report

| Property | Recorded evidence |
|---|---|
| Identity | `SCORING-METHODOLOGY-01B — Owner decision package` |
| Source | `C:\Users\Marcus\.codex\sessions\2026\10\13\rollout-2026-10-13T20-50-25-01a13550-6d7e-76a0-94e2-04fbd87124c2.jsonl` |
| Source record | JSONL line 18408, assistant `response_item` |
| Report extent | 452 extracted lines |
| Decision registry | Extracted report lines 221–235 |
| Extracted-text SHA-256 | `363D037735D54176420F5877CAB32013243D3776CE1C18467FDA9793E6BE7FF8` |
| Verification status | `VERIFIED` during `SCORING-01C-DOC-CREATION-01` |

The hash was reproduced from the exact assistant `output_text`: all
`output_text` elements were joined with a line-feed, encoded as UTF-8 without
adding a byte-order mark, and hashed with SHA-256. It is a hash of the extracted
report text, not of the complete session archive.

### 2.2 Owner-direction evidence

| Evidence | Status and limitation |
|---|---|
| Leng authorization for this record | Supplied owner statement in `C:\Users\Marcus\.codex\attachments\d91aa904-0850-4443-a08b-5b5b47b63fc7\Pasted text.txt`; SHA-256 `391B8FD63E49EFF32F0213085E9B45A19AAC2D92E174BF7ABEC81A8B4863E3B0`. It authorizes this one-file documentary record and states that all eleven owner directions are aligned. |
| Prior 01C documentary-verification instruction | Supplied at `C:\Users\Marcus\.codex\attachments\64acc69f-94d0-4135-8a36-c5df665e855c\Pasted text.txt`; SHA-256 `E85B7FEF6A2A33B0CC3391C3D63D1FB1E989E5C9BDF9464D9A14AC8DE12AA82E`. It preserves the status list and required SM-07/SM-09 clarifications, but is an instruction rather than a standalone reconciliation record. |
| Leng methodology directions | Recorded from the supplied owner authorization as alignment with the original 01B directions. No signature, message identifier, or approval timestamp is inferred beyond the supplied evidence. |
| Tai methodology positions | Reported by the supplied owner evidence as independently communicated and aligned. Tai's exact primary owner-message records were not available for independent byte-level verification when this document was created. |

The evidence above records supplied conversational owner decisions. It does
not claim cryptographic authentication of an owner's identity, signature, or
external message history.

### 2.3 Repository evidence boundaries

The reconciliation also retains these repository sources:

- `docs/proposed_method_traceability_v0.md`: conceptual scoring order,
  configuration separation, and unresolved scoring/calibration decisions.
- `docs/proposed_feature_construction_v0.md`: seven-slot evidence semantics,
  V2 admission, and the explicit absence of scoring or selection.
- `docs/proposed_hard_constraint_contract_change_v2.md`: pending HC-D04,
  HC-D05, and HC-D13 decisions.
- `docs/proposed_method_decision_log.md`: the existing decision log does not
  authorize scoring, calibration, selection, held-out work, or an evaluation
  freeze.

## 3. SM-01–SM-11 reconciliation registry

In the table below, `ALIGNED` means that the owner direction retains the 01B
recommendation and status. It does not mean that the recommendation is an
approved implementation specification.

| ID | Original 01B recommendation | Original status | Leng methodology direction | Tai independently communicated position | Reconciliation outcome | Remaining technical details | Source evidence |
|---|---|---|---|---|---|---|---|
| SM-01 | Introduce V2-native candidate score/evidence records plus a field aggregate; do not use an unsafe V1 projection. | `PROPOSED` | Retain the proposed V2-native boundary; implementation remains unauthorized. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Exact record fields, serialization, cross-runtime consumers, and shared-contract approval. | 01B lines 62–151 and 225; `docs/proposed_feature_construction_v0.md`; `docs/proposed_hard_constraint_contracts_v2.md`. |
| SM-02 | Retain c0 as the no-scoring baseline and require a feasibility gate; do not choose a formula or learned scorer yet. | `DEFER` | Retain the no-scoring reference and defer scorer selection. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Correctness labels, meaningful evidence, candidate coverage, and an approved feasibility protocol. | 01B lines 154–203 and 226; `docs/proposed_method_traceability_v0.md`. |
| SM-03 | Preserve typed evidence, explicit missingness and applicability; prohibit zero imputation. | `PROPOSED` | Preserve all seven slots and their evidence states; leave model encoding undecided. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Tensor encoding, masks, transformations, precision, and any shared-schema impact. | 01B lines 205–219 and 227; `pipeline/proposed/feature_construction.py`; `docs/proposed_feature_construction_v0.md`. |
| SM-04 | Defer scorer selection pending candidate-coverage and discriminative-signal evidence. | `DEFER` | Require a feasibility assessment before scorer selection. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Correct altered-candidate counts, class balance, feature collisions, incremental discrimination, and grouped stability. | 01B lines 163–203 and 228. |
| SM-05 | If later approved, raw score direction should mean higher values indicate stronger correctness evidence, without implying a probability or fixed range. | `PROPOSED` | Retain the proposed direction while leaving precision, range, and ties unresolved. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Numeric precision, deterministic arithmetic, score range, equality, and tie behavior. | 01B line 229; `pipeline/proposed/contracts.py`. |
| SM-06 | Use an approved companion manifest and trusted resolver for Theta_A; stored equality and declared hashes alone are insufficient. | `BLOCKED` | Retain the trusted-manifest requirement and blocked status. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Artifact format, canonical serialization, digest verification, trusted registry, runtime compatibility, and approval provenance. | 01B lines 230 and 237–273; `pipeline/proposed/contracts.py`. |
| SM-07 | Require governed semantic labels, grouped splitting, leakage protection, and feasibility evidence before training. | `BLOCKED` | Preserve distinct label states and all data-separation safeguards; final schema remains unapproved. | Reported aligned, including the clarification in Section 4; exact primary message unavailable for byte-level verification. | `ALIGNED` | Final label schema, reference normalization, governed data, grouping rules, sample sufficiency, and authorization for empirical work. | 01B lines 231 and 275–310; `docs/proposed_evaluation_protocol_v0.md`; Section 4 below. |
| SM-08 | Leave probability unavailable until a frozen scorer and validation evidence justify a calibration method. | `DEFER` | Defer Kappa selection and prohibit fabricated calibrated probability. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Calibration population, family, selection criterion, validation reuse/cross-fitting, coverage, and class support. | 01B lines 232 and 312–335; `pipeline/proposed/contracts.py`. |
| SM-09 | An ineligible c0 prohibits automatic replacement; review, failure, or a new noncommittable state remain alternatives. | `UNRESOLVED` | Retain c0 as the no-scoring reference while disabling automatic replacement. | Reported aligned, including the clarification in Section 5; exact primary message unavailable for byte-level verification. | `ALIGNED` | HC-D04, HC-D05, HC-D13, exact disposition, replacement comparison, and controller truth table. | 01B lines 233 and 337–365; `docs/proposed_hard_constraint_contract_change_v2.md`; Section 5 below. |
| SM-10 | Define Phi inputs and review reasons, but defer thresholds until scorer and calibration validation. | `DEFER` | Retain the separation of Phi from Theta_A and Kappa; defer threshold decisions. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Selective-verification inputs, thresholds, review reasons, PT1/PT2 procedure, and validation protocol. | 01B line 234; `docs/proposed_method_traceability_v0.md`. |
| SM-11 | Resolve HC-D04, HC-D05, and HC-D13 through an explicit controller truth table; conservative veto is only an option. | `UNRESOLVED` | Preserve unresolved routing and prohibit silent automatic commitment. | Reported aligned; exact primary message unavailable for byte-level verification. | `ALIGNED` | Mandatory-unavailable completeness, nonselected-candidate effects, field disposition, and receipt aggregation. | 01B lines 235 and 337–365; `docs/proposed_hard_constraint_contract_change_v2.md`. |

## 4. SM-07 clarification: labels and leakage protection

The aligned direction preserves the following proposed distinctions and
safeguards:

- `CORRECT`, `INCORRECT`, and `INDETERMINATE` are distinct proposed candidate
  label categories.
- A calendar-valid date is not automatically the correct purchase date.
- Missing or unavailable reference evidence does not imply that a candidate is
  incorrect; it requires an indeterminate or otherwise explicitly unavailable
  label state under the future approved schema.
- Related transactions, alternate captures, receipts, contributors, and other
  linked observations must be grouped and partitioned so that related evidence
  does not leak across training, validation, calibration, and held-out sets.
- Candidate coverage, correct altered-candidate availability, class balance,
  feature collisions, and incremental discriminative capability require future
  empirical investigation under separate authorization.
- Scorer fitting, configuration selection, calibration fitting, and held-out
  evaluation must remain separated under a predeclared protocol.

These are documentary methodology directions, not an approved final label
schema. Reference normalization, adjudication, grouping rules, and data-access
authority remain pending.

## 5. SM-09 clarification: permanent c0 and replacement

- Permanent c0 remains the no-scoring reference baseline.
- No artificial c0 feature vector, raw score, or calibrated probability may be
  created when the approved evidence is unavailable or ineligible.
- Automatic replacement remains disabled under the current methodology.
- Calendar validity alone cannot authorize replacement or establish receipt
  correctness.
- HC-D04, HC-D05, and HC-D13 remain unresolved.
- Future replacement, selection, review, and controller rules require separate
  approval.

Retaining c0 as a reference does not authorize automatically committing an
ineligible original value. It preserves the original candidate and its audit
history while the field follows a separately approved noncommittable, review,
or failure route.

## 6. Four recovered recommendations

### SM-02 — `DEFER`

Retain c0 as the no-scoring reference. Defer scorer selection until correctness
labels, meaningful evidence, and an approved feasibility gate exist.

### SM-03 — `PROPOSED`

Preserve all seven feature slots, typed missingness, and `NOT_APPLICABLE`
semantics. Do not use zero imputation or fabricated evidence. Model-specific
encoding remains undecided.

### SM-04 — `DEFER`

Require candidate coverage, correct altered candidates, class balance,
feature-collision analysis, and incremental discrimination evidence before
scorer selection.

### SM-08 — `DEFER`

Keep calibrated probabilities unavailable until a frozen scorer and adequate
validation evidence support an independently approved Kappa procedure.

None of these recovered recommendations is an implementation authorization.

## 7. Explicit unresolved decisions

The following remain unresolved, blocked, or deferred as indicated in the
registry:

- Exact V2 downstream score/evidence records, field aggregate, serialization,
  and version-aware consumers.
- Trusted Theta_A manifest, artifact packaging, source-byte verification,
  runtime compatibility, and approval authentication.
- Candidate-correctness reference normalization, adjudication, grouping, and
  final label schema.
- Scorer feasibility criteria, model family, objective, fitting procedure,
  feature encoding, and configuration selection.
- Numerical precision, rounding, score range, deterministic execution, and tie
  handling.
- Kappa calibration family, fitting population, validation protocol, and
  probability availability.
- Routing for rejected or unavailable c0 and unavailable altered candidates,
  including HC-D04, HC-D05, and HC-D13.
- Phi inputs, thresholds, selective-verification policy, review reasons, and
  PT1/PT2 validation-selection procedures.

This record intentionally does not resolve any item in this list.

## 8. Authorization boundary

This record grants no authorization for:

- scorer implementation, model selection, or model fitting;
- feature-method changes or a scoring experiment;
- calibration or construction of calibrated probabilities;
- real-receipt, reference, validation, calibration, or held-out data access;
- empirical evaluation or an evaluation freeze;
- automatic candidate selection, correction, replacement, or commitment;
- review-controller, persistence, Android-runtime, or production integration;
- changes to Contract V0, Contract V1/V2, D3 identities, G2A behavior,
  permanent c0, or approved Theta_A source binding.

Synthetic conformance tests, if separately authorized later, would establish
only structural behavior and would not establish statistical validity or
research effectiveness.

## 9. Closure status

`SCORING_01C_OWNER_DIRECTIONS_ALIGNED`

`SCORING_01C_DOCUMENT_CREATED_PENDING_INDEPENDENT_REVIEW`

`SCORING_METHODOLOGY_NOT_FROZEN`

`SCORING_IMPLEMENTATION_NOT_AUTHORIZED`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
