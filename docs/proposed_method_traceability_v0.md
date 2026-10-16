# PantryProof Proposed-Method Traceability and Interface Decisions V0

Status: thesis-verified implementation decision record for review. This is not a
production implementation, evaluated configuration, or held-out freeze.

## 1. Claim classes and authoritative source

Every normative statement in this document uses one of these classes:

- `THESIS_REQUIRED`: required by the approved/moderated thesis. Each occurrence
  includes a section, table or algorithm reference and both the PDF page and
  printed thesis page.
- `REPOSITORY_VERIFIED`: directly observed in checkpoint `398a996` on branch
  `setup/project-foundation`.
- `PROPOSED_DEVELOPMENT_CHOICE`: a concrete implementation choice that is
  consistent with the thesis but is not itself mandated by it.
- `UNRESOLVED`: not fixed by the thesis or repository. The entry says whether it
  blocks Task 2.3, later implementation, or formal evaluation.

### 1.1 Thesis provenance

- `THESIS_REQUIRED` - The methodological authority is *Price-Verified Grocery
  Receipt Intelligence for Malaysian Household Inventory Management*, approved/
  moderated FYP1 full text, local source
  `D:/Heng/FYP/RSW_LengWeiHeng_FullText(Moderated).pdf`. The file contains 121
  PDF pages, is unencrypted, and has SHA-256
  `77d298a16f87e81cbe23c3d746cba6a7df7d89c6485935a3bf350a24802e75a8`.
  (PDF metadata; PDF pp. 1-121.)
- `REPOSITORY_VERIFIED` - The thesis is outside the repository and was read only.
  No thesis content or receipt data was copied into a tracked data directory.
- `THESIS_REQUIRED` - For every substantive citation below, the PDF page number
  equals the printed thesis page shown in the footer. Both are nevertheless
  stated explicitly. The priority sources are Sections 3.3-3.7, 4.2-4.5,
  Tables 3.8 and 4.5-4.10, and Algorithm 4.1. (PDF pp. 40-60 and 76-105 /
  thesis pp. 40-60 and 76-105.)

### 1.2 Repository provenance and current status

- `REPOSITORY_VERIFIED` - Contract V0 is `pipeline/contracts.py` with
  `CONTRACT_VERSION = "0"`; the source adapter, B1 V1, B2 V0 and B3 V0 public
  entry points are implemented and synthetic tests exist.
- `REPOSITORY_VERIFIED` - B1, B2 and B3 manifests remain
  `PROVISIONAL_IMPLEMENTATION` with `held_out_evaluation_frozen: false` and null
  formal-freeze hashes. They must not be described as evaluation-frozen.
- `REPOSITORY_VERIFIED` - `config/`, `evaluation/`, `mobile/` and `resources/`
  contain no implemented system beyond placeholders at checkpoint `398a996`.

## 2. Exact methodological pipeline and immutable boundaries

The following is the required live-processing order. A single arrow means that
the downstream step consumes the recorded output of the preceding step; it does
not re-execute an earlier decision.

1. `THESIS_REQUIRED` - Capture or import a receipt image on the Android device;
   validate/decode it, retain the original reference and input status, then apply
   orientation handling, resizing, noise reduction and contrast enhancement
   without discarding layout geometry. Preprocessing does not independently emit
   ordinary `FALLBACK_NO_UPDATE`. (Section 3.4.1, PDF p. 43 / thesis p. 43;
   Section 3.2.4, PDF pp. 39-40 / thesis pp. 39-40.)
2. `THESIS_REQUIRED` - OCR creates one traceable image/OCR-source package linked
   to the receipt, retaining original token text, normalized text where present,
   coordinates, model-native OCR confidence and image/input status. OCR
   confidence is evidence, not a calibrated field-correctness probability.
   (Sections 3.2.4 and 3.4.2, PDF pp. 40 and 43 / thesis pp. 40 and 43;
   Table 4.2, PDF pp. 74-75 / thesis pp. 74-75.)
3. `THESIS_REQUIRED` - Execute `sourceEvidenceSufficient()` exactly once over the
   completed source package before any structured `EXTRACTED` field exists.
   Persist its result. `FALSE` is the sole ordinary source-insufficiency path and
   freezes `FALLBACK_NO_UPDATE`; catastrophic decode status is handled by this
   same gate. (Section 3.4.2, PDF p. 43 / thesis p. 43; Sections 4.1-4.2,
   PDF pp. 73-77 / thesis pp. 73-77; Algorithm 4.1 line 1, PDF p. 94 /
   thesis p. 94.)
4. `THESIS_REQUIRED` - A stored `PASS` permits the one shared B2 layout-aware
   extractor to create receipt-level and line-item fields with source links. B2 is
   reused unchanged by B3, PT1 and PT2. The proposed method consumes the stored
   gate record and must not call the gate again. (Sections 3.4.2 and 4.3.1,
   PDF pp. 43 and 82-83 / thesis pp. 43 and 82-83.)
5. `THESIS_REQUIRED` - Build an `EXTRACTED` method-ready field from the B2 field,
   its source evidence and upstream statuses. Its `original_value` is the B2
   extracted value; this becomes permanent candidate `c0`. (Section 4.3,
   PDF p. 82 / thesis p. 82; Section 4.3.2, PDF p. 92 / thesis p. 92;
   Algorithm 4.1 lines 2-3, PDF pp. 94-95 / thesis pp. 94-95.)
6. `THESIS_REQUIRED` - Detect suspicion only from upstream OCR/extractor
   confidence, missing required content, parse/type failure, line-association
   conflict and arithmetic contradiction. Every processable field still scores
   `c0`; altered candidates are generated only when suspicion is non-empty.
   (Sections 3.4.3 and 4.3.1, PDF pp. 44 and 84-85 / thesis pp. 44 and 84-85;
   Table 4.6, PDF p. 87 / thesis p. 87.)
7. `THESIS_REQUIRED` - Generate altered candidates in frozen source order,
   deduplicate while retaining provenance, apply preliminary non-price ranking,
   retain `c0`, apply `candidateLimit`, and log overflow/ties. Only candidates
   surviving the limit receive the per-candidate audit record and proceed to hard
   constraints. (Section 4.3, PDF p. 82 / thesis p. 82; Table 4.6,
   PDF pp. 87 and 90 / thesis pp. 87 and 90; Algorithm 4.1 lines 4-8,
   PDF p. 95 / thesis p. 95.)
8. `THESIS_REQUIRED` - Hard-constraint-rejected altered candidates retain their
   audit record and rejection reason but receive `NULL/NOT_APPLICABLE` raw score
   and probability, `probability_available = FALSE`, and do not enter evidence
   construction, scoring or calibration. A failed `c0` is never deleted; it
   remains auditable but cannot be automatically accepted. (Section 4.3,
   PDF p. 82 / thesis p. 82; Table 4.6, PDF p. 87 / thesis p. 87;
   Algorithm 4.1 lines 8-9 and postscript, PDF pp. 95-96 /
   thesis pp. 95-96.)
9. `THESIS_REQUIRED` - Build the fixed-order evidence vector and missingness mask
   only for candidates eligible under the preceding rule, except that `c0` remains
   in the algorithm's auditable comparison path. Reject an altered candidate
   supported solely by price before scoring. Then compute a raw score and apply
   the applicable frozen calibration configuration. (Tables 4.5-4.6,
   PDF pp. 86-90 / thesis pp. 86-90; Algorithm 4.1 lines 10-14,
   PDF p. 95 / thesis p. 95.)
10. `THESIS_REQUIRED` - Preserve nullable probability and its availability/status
    rather than fabricating a value. Under an otherwise valid probability-capable
    configuration, required per-field probability unavailability freezes `c0` as
    the pre-review prediction, marks automatic commit not permitted and routes to
    `REVIEW_REQUIRED`. Configuration-level inability to produce valid
    probabilities is `NOT_READY/NOT_VALID` and prevents held-out threshold
    routing. (Section 4.3.1, PDF pp. 84-85 / thesis pp. 84-85; Table 4.6,
    PDF p. 88 / thesis p. 88; Algorithm 4.1 lines 13 and 16-17,
    PDF p. 95 / thesis p. 95.)
11. `THESIS_REQUIRED` - Select the best candidate by calibrated correctness
    probability using a frozen deterministic tie-break. Apply the replacement
    margin/check against `c0`; revert to `c0` if the altered value fails. Only
    then freeze `pre_review_predicted_value`. (Section 4.3.2,
    PDF p. 93 / thesis p. 93; Algorithm 4.1 lines 18-20,
    PDF pp. 95-96 / thesis pp. 95-96.)
12. `THESIS_REQUIRED` - Compute `unresolvedConflict()` once after the prediction
    is frozen, pass that cached result to `confirmationRequired()`, and do not
    recompute conflict, threshold or field-impact rules inside
    `allAcceptanceChecksPass()`. The field decision freezes as `AUTO_ACCEPTED` or
    `REVIEW_REQUIRED`; processing/scoring/calibration/decision exceptions before
    disposition freeze become `FAILED/PRE_RESOLUTION`. (Table 4.6,
    PDF pp. 88-90 / thesis pp. 88-90; Algorithm 4.1 lines 20-25,
    PDF p. 96 / thesis p. 96.)
13. `THESIS_REQUIRED` - After all runtime field decisions, aggregate exactly one
    receipt-level pre-resolution disposition using only system-known states and
    precedence `FAILED/PRE_RESOLUTION > FALLBACK_NO_UPDATE > REVIEW_REQUIRED >
    AUTO_RESOLVED`. Freeze it before any reference comparison or user action.
    (Sections 3.4.6 and 3.7, PDF pp. 46 and 56-57 / thesis pp. 46 and 56-57;
    Table 4.6, PDF p. 91 / thesis p. 91.)
14. `THESIS_REQUIRED` - Tier A may replace only fields actually routed to
    `REVIEW_REQUIRED`, recording field-level `ORACLE_POLICY_RESOLVED`; automatic
    fields remain unchanged. Freeze oracle-assisted policy completion before
    reference scoring. Oracle resolution never creates production `COMMITTED`.
    (Section 3.5, PDF pp. 47-48 / thesis pp. 47-48; Algorithm 4.1 postscript,
    PDF p. 96 / thesis p. 96; Table 4.6, PDF p. 91 / thesis p. 91.)
15. `THESIS_REQUIRED` - Tier B/application review records actual
    `USER_CONFIRMED`, `USER_MODIFIED` or `REJECTED`. Only `AUTO_ACCEPTED`,
    `USER_CONFIRMED` and `USER_MODIFIED` are eligible to attempt inventory
    persistence. A successful transaction records `COMMITTED`; a write exception
    records `FAILED/INVENTORY_PERSISTENCE` without rewriting the frozen
    pre-resolution disposition. (Section 4.5, PDF pp. 104-105 /
    thesis pp. 104-105; Table 4.11, PDF pp. 106-108 /
    thesis pp. 106-108.)

### 2.1 Immutability checkpoints

| Checkpoint | Immutable content | Classification and source |
|---|---|---|
| Source package complete | Image/input state, receipt link, ordered literal OCR evidence and provenance | `THESIS_REQUIRED` - before the sole gate (Sections 3.4.1-3.4.2, PDF p. 43 / thesis p. 43). |
| Gate result recorded | One `PASS` or `FALSE`; no later rerun | `THESIS_REQUIRED` - Algorithm 4.1 lines 1 and 3 (PDF pp. 94-95 / thesis pp. 94-95). |
| Method-ready original | B2 field `original_value`, source references and permanent `c0` | `THESIS_REQUIRED` - Section 4.3 and Algorithm line 3 (PDF pp. 82 and 95 / thesis pp. 82 and 95). |
| Candidate boundary | Deduplicated bounded candidates, source tags, overflow and ties | `THESIS_REQUIRED` - Section 4.3 and Algorithm line 5 (PDF pp. 82 and 95 / thesis pp. 82 and 95). |
| Candidate audit | Constraint result, status/reason and, where applicable, evidence/score/calibration data | `THESIS_REQUIRED` - Table 4.3 and Section 4.3 (PDF pp. 78 and 82 / thesis pp. 78 and 82). |
| Pre-review prediction | `pre_review_predicted_value` after replacement reversion | `THESIS_REQUIRED` - Algorithm lines 19-20 (PDF p. 96 / thesis p. 96). |
| Field decision | `AUTO_ACCEPTED`, `REVIEW_REQUIRED` or field-level failure plus automatic commit status/reason | `THESIS_REQUIRED` - Algorithm lines 21-25 (PDF p. 96 / thesis p. 96). |
| Receipt disposition | Exactly one pre-resolution system state | `THESIS_REQUIRED` - Table 4.4 and `aggregateReceiptDisposition()` (PDF pp. 79-81 and 91 / thesis pp. 79-81 and 91). |
| Tier A policy output | Eligible oracle substitutions and completion status | `THESIS_REQUIRED` - Section 3.5 (PDF pp. 47-48 / thesis pp. 47-48). |
| Tier B/application outcome | Actual user action and later transaction result, separate from disposition | `THESIS_REQUIRED` - Section 4.5 (PDF pp. 104-105 / thesis pp. 104-105). |

## 3. Algorithm 4.1 line-by-line traceability

Owner abbreviations are `Shared`, `A` (candidate/constraint/reference lane) and
`B` (feature/scoring/calibration/policy lane). All rows are `THESIS_REQUIRED` and
cite Algorithm 4.1 (PDF pp. 94-96 / thesis pp. 94-96); supporting table citations
are included where they resolve a line.

| Line | Thesis action; input -> output | Required record; candidate/status change; exception | Dependency / owner | Minimum synthetic tests | Source |
|---:|---|---|---|---|---|
| 1 | Require completed validation, preprocessing, source package and sole gate record; require probability design ready when applicable -> admissible invocation or unavailable component | Gate/config references; a recorded `FALSE` has already produced fallback; invalid probability design is `NOT_READY/NOT_VALID`, not an invented probability | Orchestrator/config / Shared | Gate executes once; false never enters algorithm; invalid probability design blocks held-out route | Algorithm 4.1 L1, PDF p. 94 / thesis p. 94 |
| 2 | Accept one `EXTRACTED` field/entity, stored gate record, sources, `Theta_A`, `Kappa`, mode and named `Phi` -> field decision contract | Decision draft contains pre-review value, automatic commit status and disposition; PT1/PT2 identities remain distinct | Shared contracts / Shared | Reject missing/mismatched IDs or unnamed configs; preserve evaluation mode | Algorithm 4.1 L2, PDF p. 94 / thesis p. 94 |
| 3 | Assert stored `PASS` without rerunning gate; read `xf.original_value`; create and preserve `c0` -> initialized original candidate | Gate-integrity record and permanent original candidate with source evidence; absent/invalid pass returns `FAILED/PRE_RESOLUTION` reason `SOURCE_GATE_INTEGRITY` | B2-to-method adapter / Shared | No gate callback; exact B2 value becomes `c0`; invalid pass fails | Algorithm 4.1 L3, PDF p. 95 / thesis p. 95 |
| 4 | Initialize `Cf={c0}`; detect only upstream suspicion; conditionally generate altered candidates in frozen source order -> generated candidates | Suspicion reasons and pre-dedup candidate provenance; no suspicion means no altered candidates | Candidate generator / A | Every field retains `c0`; altered generation only on each allowed suspicion signal | Algorithm 4.1 L4, PDF p. 95 / thesis p. 95 |
| 5 | Deduplicate, non-price rank, apply `candidateLimit` while retaining `c0` -> bounded `Cf` | Merged provenance, rank attributes, retained/dropped status, overflow and tie audit | Candidate generator/config / A | Duplicate provenance union; price excluded from rank; `c0` survives limit; deterministic overflow | Algorithm 4.1 L5, PDF p. 95 / thesis p. 95; Table 4.6, PDF pp. 87 and 90 / thesis pp. 87 and 90 |
| 6 | Initialize audit set `Af`, probability-eligible set `Ef` and flag -> empty per-field working state | Component-local immutable accumulators/builders; no candidate status change | Orchestrator / Shared | No state leakage between fields or repeated runs | Algorithm 4.1 L6, PDF p. 95 / thesis p. 95 |
| 7 | For each retained candidate, create audit record -> candidate audit exists before evaluation | Candidate ID/value/provenance/resource refs; initially unevaluated | Candidate audit / A | Exactly one record per retained field-candidate; stable order and IDs | Algorithm 4.1 L7, PDF p. 95 / thesis p. 95 |
| 8 | Evaluate field/candidate/context hard constraints -> stored result | Typed eligibility result and reason without deleting candidate | Constraint checker / A | Field type, provenance/source, one-to-one association and arithmetic cases | Algorithm 4.1 L8, PDF p. 95 / thesis p. 95; Table 4.6, PDF p. 87 / thesis p. 87 |
| 9 | If altered candidate fails, finalize rejection and stop its downstream processing -> audited rejection | `CONSTRAINT_REJECTED`; raw/probability `NULL/NOT_APPLICABLE`; `probability_available=FALSE`; retained in `Af`, absent from evidence/scoring | Constraint-to-feature boundary / A then B | Rejected altered candidate never calls construct/score/calibrate; failed `c0` remains present but non-auto-acceptable | Algorithm 4.1 L9, PDF p. 95 / thesis p. 95; Table 4.6, PDF p. 87 / thesis p. 87 |
| 10 | Construct fixed-order evidence/mask; set price missing when unavailable -> candidate evidence | Feature values and explicit missingness; missing price is not negative | Feature builder / B | Fixed ordering; absent price marks mask only; provenance retained | Algorithm 4.1 L10, PDF p. 95 / thesis p. 95 |
| 11 | If altered value has price as sole support, reject before scoring -> price-only rejection | `REJECTED_PRICE_ONLY`, score/probability `NULL/NOT_APPLICABLE`, audit retained, iteration continues | Reference evidence plus policy-neutral support check / A-B boundary | Price cannot generate or independently authorize candidate; missing price is not sole support | Algorithm 4.1 L11, PDF p. 95 / thesis p. 95; Table 4.6, PDF p. 90 / thesis p. 90 |
| 12 | Score eligible evidence, calibrate raw score with `Kappa` -> score/calibration result | Raw score, nullable probability, availability, calibration status and reason stored | Scorer/calibrator / B | Raw score never relabelled probability; valid fitted and valid identity paths; calibration exception | Algorithm 4.1 L12, PDF p. 95 / thesis p. 95 |
| 13 | If policy-required probability set unavailable, set flag; otherwise add record to `Ef` -> eligibility for selection | Per-field probability-unavailability reason remains auditable | Calibration/policy interface / B | One missing required probability sets flag; policies that do not require it follow frozen rule | Algorithm 4.1 L13, PDF p. 95 / thesis p. 95 |
| 14 | End deterministic candidate loop -> complete `Af`, `Ef`, flag | No mutation outside ordered fold | Orchestrator / Shared | Candidate visitation order and second run are identical | Algorithm 4.1 L14, PDF p. 95 / thesis p. 95 |
| 15 | Assert audited `c0` -> continue or processing failure | Missing `c0` audit is `FAILED/PRE_RESOLUTION` | Orchestrator invariants / Shared | Deliberately omit `c0` audit and assert failure | Algorithm 4.1 L15, PDF p. 95 / thesis p. 95 |
| 16 | On required probability unavailability, freeze `c0`, deny automatic commit and return review -> frozen field decision | `pre_review_predicted_value=c0.value`, `NOT_PERMITTED`, `REVIEW_REQUIRED`, status/reason; existing stronger non-committable state is preserved | Calibration/policy / B | Nullable probability routes review; no fabricated probability; frozen value retained | Algorithm 4.1 L16, PDF p. 95 / thesis p. 95 |
| 17 | Assert `c0` participates in selection with valid probability -> continue or scoring/calibration failure | Invalid/missing `c0` scoring state becomes `FAILED/PRE_RESOLUTION` | Scorer/calibrator invariants / B | Missing/non-finite `c0` probability fails deterministically | Algorithm 4.1 L17, PDF p. 95 / thesis p. 95 |
| 18 | Select maximum probability with frozen deterministic tie-break; initialize commit denied -> provisional best | Selected candidate ID; `automatic_commit_status=NOT_PERMITTED` | Selection configuration / B | Equal probability uses frozen tie rule; no iteration-order accident | Algorithm 4.1 L18, PDF p. 95 / thesis p. 95 |
| 19 | If altered best fails replacement rule/margin against `c0`, revert -> final candidate before freeze | Replacement result/reason; best becomes `c0` when rule fails | `Theta_A` replacement rule / B | Boundary equality for margin; failed altered replacement reverts exactly to `c0` | Algorithm 4.1 L19, PDF p. 96 / thesis p. 96 |
| 20 | Freeze selected value -> immutable pre-review prediction | `pre_review_predicted_value`; later conflict/review/oracle/user actions cannot rewrite it | Field decision / Shared | Mutation attempts rejected; review retains value | Algorithm 4.1 L20, PDF p. 96 / thesis p. 96 |
| 21 | If selected best is constraint-ineligible, return review -> frozen review decision | `REVIEW_REQUIRED`, commit remains denied; most importantly covers retained failed `c0` | Policy / B | Constraint-ineligible `c0` is audited/scored as defined but cannot auto-accept | Algorithm 4.1 L21, PDF p. 96 / thesis p. 96 |
| 22 | Compute conflict once, call `confirmationRequired` using cached result and `Phi`; review if required -> review or no-review controller result | Conflict audit plus cached controller outcome | Selective policy / B | Conflict called exactly once; threshold/impact and unavailable-probability paths; cache reused | Algorithm 4.1 L22, PDF p. 96 / thesis p. 96; Table 4.6, PDF pp. 88-89 / thesis pp. 88-89 |
| 23 | Run acceptance conjunction using cached no-review outcome; altered replacement must have passed, `c0` replacement is N/A -> automatic acceptance | `automatic_commit_status=PERMITTED`; field `AUTO_ACCEPTED` | Acceptance policy / B | Cannot accept with failed provenance/constraint/conflict/threshold/impact; no recomputation | Algorithm 4.1 L23, PDF p. 96 / thesis p. 96; Table 4.6, PDF p. 90 / thesis p. 90 |
| 24 | Default any remaining processable case to review -> review decision | `REVIEW_REQUIRED`, automatic commit denied | Policy / B | Exhaustive state test ensures no implicit auto acceptance | Algorithm 4.1 L24, PDF p. 96 / thesis p. 96 |
| 25 | Catch processing/scoring/calibration/decision exception before disposition freeze -> pre-resolution failure; persistence remains downstream | `FAILED`, `failure_stage=PRE_RESOLUTION`; later write failure uses `INVENTORY_PERSISTENCE` and never mutates algorithm output/disposition | Orchestrator and persistence boundary / Shared | Fault injection at every stage; no commit; receipt aggregation precedence; later write failure remains separate | Algorithm 4.1 L25, PDF p. 96 / thesis p. 96 |

`PROPOSED_DEVELOPMENT_CHOICE` - Treat Algorithm line 9 as terminating processing
for that altered candidate (a semantic `CONTINUE`). Although line 9 does not print
the word `CONTINUE`, Table 4.6 explicitly says not to call `constructEvidence()`,
`score()` or `calibrate()` for it, and Sections 4.2-4.3 repeat that exclusion.
(Supporting authority: Table 4.6, PDF p. 87 / thesis p. 87; Section 4.3,
PDF p. 82 / thesis p. 82.)

## 4. Permanent `c0` and B3 compatibility decision

- `THESIS_REQUIRED` - `xf.original_value` is the original extracted value of the
  method-ready field produced after the stored gate `PASS` and shared B2
  extraction. It is not an already corrected or normalized B3 value. `c0` is
  created from this value with source `ORIGINAL` and remains available even when
  constraint-ineligible. (Section 4.3, PDF p. 82 / thesis p. 82;
  Section 4.3.2, PDF p. 92 / thesis p. 92; Algorithm line 3,
  PDF p. 95 / thesis p. 95.)
- `THESIS_REQUIRED` - Generic normalization is the second altered-candidate
  source, after source/neighbour token alternatives. It may produce a value that
  differs from `c0`, but it must not overwrite `c0`. (Section 4.3,
  PDF p. 82 / thesis p. 82; Table 4.6, PDF p. 87 / thesis p. 87.)
- `REPOSITORY_VERIFIED` - Current `B3Result` retains both `original_b2_result`
  and per-field `original_field`/`transformed_field` relationships, but its
  `receipt_output` contains B3-transformed values. Feeding that transformed
  output into Algorithm 4.1 as `original_value` would violate the thesis `c0`
  boundary.
- `PROPOSED_DEVELOPMENT_CHOICE` - Task 2.3 should define an immutable
  `MethodReadyFieldV1`/adapter that takes the B2 `StructuredField` as the original
  and permanent `c0`, and takes applicable B3 rule events/transformations as
  generic candidate seeds and audit provenance. The adapter must never replace
  `c0` in place.
- `PROPOSED_DEVELOPMENT_CHOICE` - Keep `apply_b3()` unchanged for the B3
  comparator. The proposed path may invoke the same frozen rules through an
  adapter or a conformance-proven shared rule kernel, but the exact B3 comparator
  output and manifest must not acquire retailer, price, scoring, calibration or
  abstention behavior.
- `UNRESOLVED` - Whether to call `apply_b3()` and adapt its result, or extract a
  separately shared pure generic-rule kernel, is an implementation choice. It is
  non-blocking for Task 2.3 if the shared interface fixes the B2-as-`c0` invariant
  and requires frozen B3 conformance fixtures. It must be decided before the
  proposed orchestrator is implemented.

`REPOSITORY_VERIFIED` - The unmodified transcription remains auditable through
Contract V0 `OcrSourceToken.original_text`, the B2 field's `source_token_ids`,
the permanent `c0` candidate and the proposed typed candidate provenance.

## 5. Candidate priority, ranking and limit

### 5.1 Source priority and provenance

`THESIS_REQUIRED` - Altered candidate generation uses this exact priority
(Section 4.3, PDF p. 82 / thesis p. 82; Table 4.6, PDF p. 87 /
thesis p. 87):

1. source-token or neighbouring-token alternatives;
2. generic normalization;
3. retailer mapping; and
4. pantry terminology.

Price/reference evidence never generates a candidate value. Candidates are
deduplicated by normalized field-compatible value while retaining every source
tag. (Section 4.3, PDF p. 82 / thesis p. 82; Table 4.6,
PDF p. 87 / thesis p. 87.)

`PROPOSED_DEVELOPMENT_CHOICE` - A candidate provenance entry should minimally
contain `source_kind`, resource/version ID where applicable, source token IDs and
exact character slices where available, neighbouring-token relation/source-order
position, producing rule ID, and original observed value. Deduplication creates
one candidate ID and an ordered union of provenance entries rather than choosing
one source.

### 5.2 Preliminary non-price tuple

`THESIS_REQUIRED` - Rank altered candidates by the following tuple
(Section 4.3, PDF p. 82 / thesis p. 82; Table 4.6, PDF p. 90 /
thesis p. 90):

1. declared source-priority rank;
2. decreasing normalized edit similarity to `c0`;
3. smallest source-order displacement; and
4. ascending normalized candidate text.

Price, hard-constraint results and later supporting checks are excluded from this
ranking. Retain `c0` independently of its altered-candidate rank. Apply the
validation-frozen total `candidateLimit` after deduplication/ranking and before
hard constraints; log overflow candidates and tie values. (Section 4.3,
PDF p. 82 / thesis p. 82; Table 4.6, PDF pp. 87 and 90 /
thesis pp. 87 and 90; Algorithm line 5, PDF p. 95 / thesis p. 95.)

- `UNRESOLVED` - The numeric limit or predeclared candidate grid, validation
  objective and tie rule have not been selected. This blocks candidate-engine
  configuration/fitting, not Task 2.3 record definitions. Selection must use the
  declared validation route and never held-out outcomes. (Table 4.6,
  PDF p. 87 / thesis p. 87.)
- `UNRESOLVED` - The exact field-compatible normalization function, edit-
  similarity formula and source-order displacement formula are not fully defined
  in the thesis. They block candidate-engine implementation and require a
  reviewed development specification before coding.
- `PROPOSED_DEVELOPMENT_CHOICE` - Audit both sides of the bound: retained
  candidate IDs with complete ranking tuple and dropped candidate IDs with
  `LIMIT_OVERFLOW`, rank, tie group and provenance. This makes the validation-
  selected limit reproducible without scoring dropped candidates.

## 6. Hard constraints and candidate audit semantics

| Rule | Required behavior | Record scope | Classification and source |
|---|---|---|---|
| Field type validity | Candidate must satisfy the field's declared type/parse rules | Shared constraint result | `THESIS_REQUIRED` - Table 4.5 and Table 4.6 (PDF pp. 86-87 / thesis pp. 86-87). |
| One-to-one association | Candidate must retain an unambiguous field/line relationship | Shared constraint result with source links | `THESIS_REQUIRED` - Table 4.6 (PDF p. 87 / thesis p. 87). |
| Source support | Altered value requires declared provenance; source evidence is never overwritten | Shared candidate provenance | `THESIS_REQUIRED` - Sections 4.1 and 4.3 (PDF pp. 74 and 82 / thesis pp. 74 and 82). |
| Arithmetic/tolerance | Apply field-compatible quantity/unit-price/line-total/receipt rules and explicit exceptions; unresolved contradiction cannot authorize automatic replacement | Shared constraint result; optional diagnostic detail local to checker | `THESIS_REQUIRED` - Sections 3.4.4 and 4.3 (PDF pp. 44-45 and 93 / thesis pp. 44-45 and 93); Tables 4.7 and 4.10 (PDF pp. 97 and 103 / thesis pp. 97 and 103). |
| Price-only support | Price alone neither generates nor authorizes an altered value | Shared candidate status `REJECTED_PRICE_ONLY` | `THESIS_REQUIRED` - Algorithm line 11 and `priceIsSoleSupport()` (PDF pp. 95 and 90 / thesis pp. 95 and 90). |
| Missing optional evidence | Preserve missingness; absence alone triggers neither review nor fallback | Evidence mask/local source availability record | `THESIS_REQUIRED` - Table 4.7 and Table 4.14 (PDF pp. 97 and 112-113 / thesis pp. 97 and 112-113). |
| Failed altered candidate | Retain audit; never construct evidence, score or calibrate | Shared status `CONSTRAINT_REJECTED`; raw/probability N/A | `THESIS_REQUIRED` - Section 4.3 and Table 4.6 (PDF pp. 82 and 87 / thesis pp. 82 and 87). |
| Failed `c0` | Preserve value/provenance but prohibit automatic acceptance | Shared constraint result on permanent `c0` | `THESIS_REQUIRED` - Algorithm postscript (PDF p. 96 / thesis p. 96). |

`PROPOSED_DEVELOPMENT_CHOICE` - Task 2.3 should distinguish three concepts:

- constraint eligibility (`ELIGIBLE` or `CONSTRAINT_REJECTED`);
- later support status (`REJECTED_PRICE_ONLY`); and
- scoring/calibration applicability (`AVAILABLE`, `UNAVAILABLE`, or
  `NOT_APPLICABLE`).

`UNRESOLVED` - The thesis mandates a reason but does not enumerate a complete
machine-readable rejection-code vocabulary. Task 2.3 should define a minimal
extensible enum for the named categories above plus a non-empty detail field;
the exact field-specific rule IDs/tolerances must be frozen before candidate-
engine implementation.

## 7. Feature construction and raw scoring

### 7.1 Frozen conceptual feature order

`THESIS_REQUIRED` - Equation 4.1 fixes the conceptual order as
`[q_o, q_e, a_l, a_y, s_r, s_a, s_p]` (Section 4.3.2,
PDF p. 92 / thesis p. 92), corresponding to:

| Slot | Meaning | Runtime provenance | Availability/type decision |
|---|---|---|---|
| `q_o` | OCR evidence/confidence | Original OCR token record(s) | Thesis identifies confidence evidence; exact aggregation, range and numeric normalization are `UNRESOLVED`. |
| `q_e` | Extractor evidence/confidence | Frozen B2 field/association output | Thesis identifies extraction confidence; current B2 generally emits no field confidence. Exact value/range is `UNRESOLVED`. |
| `a_l` | Lexical agreement | Candidate, `c0`, literal source and declared terminology | Exact similarity/encoding is `UNRESOLVED`; generic and pantry terminology source tags must remain distinguishable. |
| `a_y` | Layout/spatial agreement | B2 source polygons, line/item association and candidate source | Exact numeric/categorical encoding is `UNRESOLVED`. |
| `s_r` | Retailer support | Versioned retailer mapping snapshot | Optional; unavailable stays missing. Exact encoding is `UNRESOLVED`. |
| `s_a` | Arithmetic consistency/support | Quantity, unit price, line total, receipt total and exception status | Exact categorical/numeric encoding and tolerances are `UNRESOLVED`. |
| `s_p` | Malaysian price/reference agreement | Versioned reference snapshot and observed date/value | Optional, non-authoritative and missing-aware. Exact discrepancy feature is `UNRESOLVED`. |

`THESIS_REQUIRED` - The conceptual meanings are required by Section 3.4.4 and
Equation 4.1.
(PDF pp. 44-45 and 92 / thesis pp. 44-45 and 92.) Precise feature types,
scales and encodings are not supplied by the thesis and must not be invented in
this document.

- `THESIS_REQUIRED` - The feature vector and corresponding missingness mask are
  constructed only after applicable hard-constraint eligibility. Missing signals
  remain missing rather than negative; price availability is explicitly masked.
  (Section 3.4.4, PDF pp. 44-45 / thesis pp. 44-45; Table 4.6,
  PDF p. 87 / thesis p. 87.)
- `THESIS_REQUIRED` - Generic normalization and pantry terminology are candidate
  sources/provenance. The thesis does not add separate eighth or ninth Equation
  4.1 slots for them; any influence on lexical/support evidence must preserve
  those source tags. (Section 4.3 and Equation 4.1, PDF pp. 82 and 92 /
  thesis pp. 82 and 92.)
- `THESIS_REQUIRED` - Scorer/model parameters are fitted on training data;
  permitted hyperparameter/configuration selection uses validation only. The
  dated manifest freezes model family, feature order, missingness treatment,
  fitting subset and selection route before held-out evaluation. (Sections 3.3
  and 3.4.4, PDF pp. 40-45 / thesis pp. 40-45; Table 4.6,
  PDF p. 88 / thesis p. 88.)
- `UNRESOLVED` - The scorer family is not selected by the thesis. It must be
  chosen through a predeclared development/validation route and frozen; no
  dependency should be added before that decision. This blocks scoring
  implementation, not Task 2.3 interface definitions.
- `PROPOSED_DEVELOPMENT_CHOICE` - Task 2.3 should represent the seven slots as an
  ordered schema ID plus typed nullable feature entries and a same-length Boolean
  missingness mask, rather than assuming all final encodings are floats now.

`PROPOSED_DEVELOPMENT_CHOICE` - The scorer input is one constraint-eligible
candidate's frozen ordered evidence and mask plus a `Theta_A` reference. Its
output is a finite raw comparative score and scorer status. Raw OCR confidence,
extractor confidence and the raw scorer output must never be labelled calibrated
correctness probabilities.

## 8. Configuration and calibration ownership

| Configuration | Owns | Must not own | Classification and source |
|---|---|---|---|
| `Theta_A` automatic-method configuration | Candidate limit/grid, feature schema/order and missingness treatment, scorer/model family and hyperparameters, deterministic candidate selection/tie rules, replacement margin `m` and other settings capable of changing `pre_review_predicted_value` | Review-only acceptance threshold or oracle behavior | `THESIS_REQUIRED` - Section 4.3.2 and Table 4.13 (PDF pp. 93 and 111-112 / thesis pp. 93 and 111-112). |
| `Kappa` calibration configuration | Raw-score-to-candidate-correctness-probability interpretation; fitted mapping from validation predictions where applicable, or justified identity/no-calibration only for an already bounded correctness probability | Candidate generation, raw scoring, policy threshold, fabricated values | `THESIS_REQUIRED` - Sections 3.3 and 4.3.2 (PDF pp. 41 and 92-93 / thesis pp. 41 and 92-93). |
| `Phi` selective-policy configuration | Acceptance threshold `tau`, conflict tolerance, field-impact/review-only rules and named policy identity | CandidateLimit, scorer fitting or replacement margin that changes the frozen prediction | `THESIS_REQUIRED` - Section 4.3.2 and Table 4.6 (PDF pp. 93 and 88-89 / thesis pp. 93 and 88-89). |
| PT1 comparison configuration | Validation-selected common-coverage comparison point/status and tolerance relative to B3 fixed non-selective validation coverage | PT2 threshold or oracle substitution | `THESIS_REQUIRED` - Table 4.6 (PDF p. 89 / thesis p. 89). |
| PT2 operating configuration | Validation-selected selective operating point or explicit `NO_VALID_POINT` | PT1 common-coverage choice or post-hoc held-out threshold | `THESIS_REQUIRED` - Table 4.6 (PDF p. 89 / thesis p. 89). |

Additional required semantics:

- `THESIS_REQUIRED` - Calibration estimates candidate correctness; it does not
  guarantee correctness. A raw score is not a probability. (Section 4.3.1,
  PDF pp. 84-85 / thesis pp. 84-85.)
- `THESIS_REQUIRED` - Configuration-level invalidity is
  `NOT_READY/NOT_VALID` and blocks probability-threshold held-out execution. A
  per-field runtime failure under an otherwise valid design preserves nullable
  probability, availability/status/reason and routes to review unless a stronger
  non-committable state already applies. (Section 4.3.1, PDF p. 85 /
  thesis p. 85.)
- `THESIS_REQUIRED` - Replacement requires hard constraints, non-price support
  and `p(altered) - p(c0) >= m`. Automatic acceptance requires an eligible
  candidate, `p(best) >= tau`, no cached unresolved conflict and the frozen
  field-impact checks. (Section 4.3.2, PDF p. 93 / thesis p. 93;
  Table 4.6, PDF p. 88 / thesis p. 88.)
- `UNRESOLVED` - No numeric `m`, `tau`, conflict tolerance, candidate limit or
  calibration method is authorized yet. Their grids, objectives and tie rules
  must be declared before validation and frozen before held-out access.

## 9. PT1 and PT2 decision boundaries

### 9.1 PT1 - Proposed Automatic comparison

- `THESIS_REQUIRED` - PT1 is the pre-review automatic output and system-side
  disposition with no user/oracle substitution. It can visibly contain
  `AUTO_RESOLVED`, `REVIEW_REQUIRED`, `FALLBACK_NO_UPDATE` or `FAILED`.
  (Table 3.8, PDF p. 49 / thesis p. 49.)
- `THESIS_REQUIRED` - Select on validation the common-coverage configuration
  nearest B3's fixed non-selective validation coverage within the predefined
  tolerance. No valid pair means PT1 is `NOT_ASSESSABLE`. (Table 4.6,
  PDF p. 89 / thesis p. 89; Section 3.7.1, PDF p. 60 / thesis p. 60.)
- `THESIS_REQUIRED` - If a valid common-coverage comparison exists but B3
  automatic CIER is zero, relative reduction is `NOT_ASSESSABLE`; do not invent
  a percentage. Report absolute risk difference, counts and uncertainty.
  (Section 3.7 and Table 3.11, PDF pp. 56 and 58-60 /
  thesis pp. 56 and 58-60.)
- `THESIS_REQUIRED` - Primary RQ1 is paired PantryProof-versus-B3 common-schema
  micro-F1 plus the separately frozen PT1 automatic-CIER comparison. B1 and B2
  remain mandatory supporting comparisons. (Sections 3.6-3.7,
  PDF pp. 48-60 / thesis pp. 48-60.)

### 9.2 PT2 - Proposed Selective Policy

- `THESIS_REQUIRED` - PT2 uses the same underlying automatic method under a
  separately frozen operating configuration. Tier A oracle substitution is
  allowed only after routing and only for actual `REVIEW_REQUIRED` fields.
  (Table 3.8, PDF p. 49 / thesis p. 49.)
- `THESIS_REQUIRED` - Among predeclared validation points, choose the point with
  the lowest field-level confirmation rate whose upper 95% bootstrap bound for
  Tier A oracle-assisted residual CIER does not exceed B3 automatic validation
  CIER under B3's fixed non-selective disposition semantics. (Table 3.11,
  PDF p. 59 / thesis p. 59; Table 4.6, PDF p. 89 / thesis p. 89.)
- `THESIS_REQUIRED` - If no point qualifies, freeze `NO_VALID_POINT`, classify
  PT2 `NOT_ASSESSABLE`, and do not apply any PT2 threshold to held-out RQ2.
  (Section 3.7.1, PDF pp. 59-60 / thesis pp. 59-60.)
- `THESIS_REQUIRED` - The field-level confirmation denominator is system-side
  pantry-relevant field decisions eligible for automatic acceptance or review;
  its numerator is those routed to `REVIEW_REQUIRED`. Hidden undetected lines,
  fallback and failure are not confirmation opportunities. (Table 3.9 and
  Section 3.7, PDF pp. 53-54 / thesis pp. 53-54.)

`THESIS_REQUIRED` - PT1 and PT2 cannot share an arbitrarily selected acceptance
threshold because their validation objectives differ: PT1 selects a B3 common-
coverage comparison configuration for RQ1, while PT2 minimizes confirmation
subject to an oracle-assisted residual-CIER bound for RQ2. (Section 3.7.1,
PDF pp. 58-60 / thesis pp. 58-60; Table 4.6, PDF p. 89 /
thesis p. 89.)

### 9.3 Field and receipt states

- `THESIS_REQUIRED` - `AUTO_ACCEPTED` is a field decision with
  `automatic_commit_status=PERMITTED`; `AUTO_RESOLVED` is a receipt-level
  aggregation requiring every system-required/emitted field to be permitted and
  no review/fallback/pre-resolution failure. (Algorithm line 23,
  PDF p. 96 / thesis p. 96; Section 3.7, PDF pp. 56-57 /
  thesis pp. 56-57.)
- `THESIS_REQUIRED` - An automatic correction attempt exists only when frozen
  `pre_review_predicted_value != c0`. Successful corrections and introduced
  errors additionally require automatic commit permitted and later reference
  comparison; unchanged wrong `c0` is an extraction error, not a correction
  attempt. (Table 3.9 and Section 3.7, PDF pp. 53-55 /
  thesis pp. 53-55.)
- `THESIS_REQUIRED` - Oracle/reference truth is prohibited from candidate
  generation, routing, automatic disposition and coverage. It is consulted only
  after those outputs freeze. (Sections 3.5 and 3.7,
  PDF pp. 47-50 / thesis pp. 47-50.)

## 10. Human review, resolution and persistence

| Construct | Required distinction | Classification and source |
|---|---|---|
| Frozen pre-review prediction | Selected automatic value after replacement reversion; remains present during review | `THESIS_REQUIRED` - Algorithm lines 19-20 and postscript (PDF p. 96 / thesis p. 96). |
| Frozen field decision | `AUTO_ACCEPTED`, `REVIEW_REQUIRED` or failure, reason and automatic commit status | `THESIS_REQUIRED` - Section 4.3 and Algorithm 4.1 (PDF pp. 82 and 94-96 / thesis pp. 82 and 94-96). |
| Frozen receipt disposition | Exactly one system-only pre-resolution aggregation | `THESIS_REQUIRED` - Table 4.3 and Table 4.6 (PDF pp. 79 and 91 / thesis pp. 79 and 91). |
| Tier A oracle resolution | `ORACLE_POLICY_RESOLVED` only for actual review; evaluation-only, no production commit | `THESIS_REQUIRED` - Table 4.4 (PDF p. 80 / thesis p. 80). |
| Tier B confirmation | `USER_CONFIRMED` accepts the presented value after actual user action | `THESIS_REQUIRED` - Table 4.4 (PDF p. 80 / thesis p. 80). |
| Tier B modification | `USER_MODIFIED` stores actual user-supplied value after review | `THESIS_REQUIRED` - Table 4.4 (PDF p. 80 / thesis p. 80). |
| Rejection | `REJECTED` creates no inventory commitment and retains disposition | `THESIS_REQUIRED` - Table 4.4 (PDF p. 81 / thesis p. 81). |
| Automatic commit permission | Field `AUTO_ACCEPTED` and receipt eligibility permit a later attempt; permission is not a database result | `THESIS_REQUIRED` - Section 4.5 (PDF p. 104 / thesis p. 104). |
| Committed transaction | Only a successful inventory write records `COMMITTED` | `THESIS_REQUIRED` - Section 4.5 (PDF pp. 104-105 / thesis pp. 104-105). |
| Persistence failure | Write exception records `FAILED/INVENTORY_PERSISTENCE`, no `COMMITTED`, no disposition mutation | `THESIS_REQUIRED` - Section 4.5 (PDF pp. 104-105 / thesis pp. 104-105). |

`THESIS_REQUIRED` - Required immutable/append-only audit includes the receipt and
line-item IDs, source token evidence, original value and `c0`, bounded candidates
and candidate evidence, frozen pre-review value, decision/reason, pre-resolution
disposition, every presented review field, Accept/Edit/Reject action, user or
oracle resolution source, inventory source-decision links, transaction result,
and stage-qualified failure. SQLite must enforce the eventual frozen keys,
foreign keys, nullability, schema/migration version and indexes. (Section 4.1
and Tables 4.11-4.12,
PDF pp. 76 and 106-110 / thesis pp. 76 and 106-110.)

`REPOSITORY_VERIFIED` - Contract V0 correctly says that a non-empty write
reference is not proof of transaction success and permits persistence only after
`AUTO_RESOLVED`. It has no user-resolution eligibility path yet.

## 11. Evaluation and baseline-fairness safeguards

- `THESIS_REQUIRED` - All methods use the same eligible receipts, preprocessing
  and OCR outputs. B3, PT1 and PT2 reuse the exact B2 extractor without refitting
  or changed decoding after held-out access. (Section 3.4.2,
  PDF p. 43 / thesis p. 43; Table 4.8, PDF pp. 98-100 /
  thesis pp. 98-100.)
- `THESIS_REQUIRED` - The common primary schema is store name, purchase date,
  receipt item description, quantity, unit price where reference-available for
  evaluator scoring, line total and receipt total. Receipt item description is
  distinct from optional pantry-normalized semantic identity. (Sections 3.4.2
  and 3.7, PDF pp. 44 and 50-54 / thesis pp. 44 and 50-54;
  Table 4.8, PDF pp. 98-100 / thesis pp. 98-100.)
- `THESIS_REQUIRED` - Unit-price reference availability is evaluator-side and is
  distinct from optional retailer/product price-reference evidence. Runtime code
  cannot consult adjudicated availability. (Tables 4.6 and 4.9,
  PDF pp. 91 and 101 / thesis pp. 91 and 101.)
- `THESIS_REQUIRED` - Partition eligible receipts 60% training, 20% validation
  and 20% held-out after grouping exact/near duplicates, alternate captures,
  related transactions and contributor clusters. All receipts from one
  contributor stay in one partition. Freeze unseen-retailer eligibility before
  outcomes. (Section 3.3, PDF pp. 40-41 / thesis pp. 40-41.)
- `THESIS_REQUIRED` - The deterministic one-to-one item matcher is selected on a
  training-only protocol subset excluded from scorer/extractor fitting, then
  frozen before validation. Exact normalized-description matches precede
  thresholded Levenshtein matching under monotonic source order; no many-to-one
  matching is allowed. (Section 3.2.3, PDF p. 39 / thesis p. 39.)
- `THESIS_REQUIRED` - A completely undetected purchased line creates no runtime
  field, review or fallback state. After disposition freeze it is an unmatched
  false negative, fails receipt exact match and may be omission CIER. (Section
  3.7, PDF pp. 50 and 56 / thesis pp. 50 and 56; Table 4.7,
  PDF p. 98 / thesis p. 98.)
- `THESIS_REQUIRED` - Resource mappings/snapshots come from pre-existing sources
  or training data only; calibration where applicable uses validation
  predictions from the frozen scorer; policy selection is validation-only;
  held-out data only evaluate the fully frozen system. (Table 3.7,
  PDF p. 48 / thesis p. 48.)
- `THESIS_REQUIRED` - B3 stays a substantive non-selective generic-rule baseline:
  it receives no retailer-specific mappings, Malaysian price evidence,
  calibrated review or abstention. Its diagnostics do not remove predictions.
  (Tables 3.8, 4.8 and 4.10, PDF pp. 49, 99 and 102-103 /
  thesis pp. 49, 99 and 102-103.)
- `THESIS_REQUIRED` - Tier A supports automatic comparison and evaluation-only
  oracle policy analysis; Tier B records realized user behavior; SROIE is a
  separate external OCR/key-information benchmark and cannot support Malaysian
  pantry CIER, retailer, price or selective-verification claims. (Sections 3.8
  and 4.2, PDF pp. 61 and 81 / thesis pp. 61 and 81.)
- `REPOSITORY_VERIFIED` - B1/B2/B3 are implemented but still provisional. Formal
  freeze must add exact commit/config/resource/OCR identifiers, implementation
  and manifest hashes, split/data provenance and conformance fixture hashes.

## 12. Contract V0 reuse and Task 2.3 interface decisions

### 12.1 Reuse without changing Contract V0

| Existing record | Decision | Rationale |
|---|---|---|
| `Point`, `SourceProvenance`, `OcrSourceToken` | Reuse Contract V0 | `REPOSITORY_VERIFIED` - preserves literal source evidence and model-native confidence. |
| `SourceEvidenceGateResult`, `ReceiptSourceEvidence` | Reuse Contract V0 | `REPOSITORY_VERIFIED` - records the gate result and source package; orchestration must still guarantee exactly-once execution. |
| `StructuredField`, `ReceiptItemRow`, `ReceiptOutput` | Reuse Contract V0 as B2 source | `REPOSITORY_VERIFIED` - provides seven-field structure, IDs, missing/unresolved state and source-token references. It is not the final method decision. |
| `ExternalPriceReference` | Reuse as a leaf value where sufficient | `REPOSITORY_VERIFIED` - availability/provenance separation is useful; resource snapshot and candidate linkage need a wrapper. |
| `PreResolutionDisposition` | Reuse for receipt aggregation | `REPOSITORY_VERIFIED` - already preserves gate consistency and frozen system state. |
| `PersistenceOutcome` | Reuse only for the existing automatic path | `REPOSITORY_VERIFIED` - shape guard is sound, but user-resolved eligibility needs a later versioned relationship. |

`REPOSITORY_VERIFIED` - `CandidateValue` and `CorrectionEvidence` preserve a
basic original/alternative relationship, but lack candidate IDs, typed source
priority/provenance, constraint results, limit audit, vector/mask, scores,
calibration state and field decision semantics. They must not be stretched with
free-form strings to represent the full method.

### 12.2 Component-local immutable wrappers

`PROPOSED_DEVELOPMENT_CHOICE` - Keep these local until their algorithms are
selected:

- raw pre-dedup candidate seed and generator diagnostics;
- candidate ranking working tuple and internal dedup accumulator;
- field-specific arithmetic/layout diagnostic details beyond the shared reason;
- scorer-native tensors/model inputs and calibration-library objects;
- resource lookup/cache implementation details; and
- Android/SQLite transport entities generated from the shared records.

### 12.3 Smallest versioned shared interface set for Task 2.3

`PROPOSED_DEVELOPMENT_CHOICE` - Add new proposed-system records in a new module,
without modifying Contract V0:

1. `MethodReadyFieldV1`: B2 field reference, exact `original_value`, permanent
   `c0` ID, stored gate-result ID, upstream evidence/suspicion statuses and B3-
   compatibility reference.
2. `CandidateProvenanceV1` and `CandidateRecordV1`: stable candidate ID, value,
   original/altered flag, source kind/priority, ordered provenance, normalized
   dedup key, rank attributes, retained/overflow status and resource version.
3. `ConstraintResultV1`: candidate ID, eligibility, rule IDs and non-empty reason.
4. `CandidateEvidenceV1`: one post-limit audit record joining provenance,
   constraint/status, optional ordered feature schema/vector/mask, nullable raw
   score, nullable calibrated probability, availability/status/reason and config
   references. Rejected candidates enforce N/A score/probability.
5. `FieldDecisionV1`: field/candidate IDs, immutable original and `c0`, frozen
   pre-review value, field decision, automatic commit status, reason, cached
   conflict outcome and `Theta_A`/`Kappa`/`Phi` references.
6. `ConfigurationRefsV1`: distinct versioned/hash references for `Theta_A`,
   `Kappa`, `Phi`, PT1 and PT2, including readiness/validity/no-valid-point status.
7. `ReviewResolutionV1`: mandatory resolution source, actual prior field decision,
   mutually exclusive oracle or user value, and confirmed/modified/rejected state.
8. `FinalApplicationOutcomeV1`: frozen pre-resolution disposition reference,
   eligible automatic/user resolution reference, transaction result and
   stage-qualified persistence failure without disposition overwrite.

`PROPOSED_DEVELOPMENT_CHOICE` - The shared records should use immutable values,
stable IDs, closed enums plus explicit version fields, and reject non-finite
numeric values. Exact serialization format remains a Task 2.3 decision but must
be language-neutral enough for Android conformance fixtures.

## 13. Two-member split recommendation

`PROPOSED_DEVELOPMENT_CHOICE` - The Task 2.1 division remains valid with one
adjustment: B3-to-method adaptation is shared because it defines the permanent
`c0` boundary.

### Team Member A - candidate, constraints and resources

Owned proposed modules:

- `pipeline/proposed/candidates.py`
- `pipeline/proposed/constraints.py`
- `pipeline/proposed/reference_evidence.py`
- matching unit-test modules and candidate/resource documentation

Inputs: `MethodReadyFieldV1`, B2/B3 compatibility fixture, resource snapshot
interfaces and `Theta_A` candidate settings.

Outputs: bounded `CandidateRecordV1` collection, overflow/tie audit,
`ConstraintResultV1`, typed reference availability/provenance and price-only
support result.

Synthetic fixtures: every candidate source priority, dedup provenance union,
candidate-limit boundaries, `c0` retention, overflow/ties, each constraint,
price-only rejection, absent retailer/price resources and deterministic replay.

### Team Member B - evidence, scoring, calibration and policy

Owned proposed modules:

- `pipeline/proposed/features.py`
- `pipeline/proposed/scoring.py`
- `pipeline/proposed/calibration.py`
- `pipeline/proposed/policy.py`
- matching unit-test modules and scoring/policy documentation

Inputs: retained candidate plus constraint result, source/context evidence,
optional reference evidence, feature schema and distinct config references.

Outputs: `CandidateEvidenceV1`, raw score/calibration state,
`FieldDecisionV1`, and PT1/PT2 configuration-selection result types.

Synthetic fixtures: fixed feature order/mask, rejection bypass, raw-score versus
probability separation, config invalidity, per-field unavailability, deterministic
ties, replacement-margin boundaries, one cached conflict call, PT1 zero-CIER and
PT2 `NO_VALID_POINT`.

### Shared work and earliest split

The following remain shared/single-owner:

- `pipeline/proposed/contracts.py` and its invariant tests;
- B2-to-method/B3-compatibility adapter and golden fixtures;
- exactly-once gate/orchestrator and receipt aggregation;
- integration/evaluation schemas and configuration manifests;
- review/persistence contracts; and
- all changes to package exports.

`PROPOSED_DEVELOPMENT_CHOICE` - The earliest safe split is after Task 2.3 has
implemented and both members have approved the eight shared record groups above,
the Algorithm line-9 skip invariant, stable synthetic cross-lane fixtures and the
B2-as-`c0` adapter contract. Member A and B may then work independently against
those fixtures. Neither member may change B1/B2/B3 semantics or Contract V0
unilaterally.

## 14. Android deployment decisions

- `THESIS_REQUIRED` - The evaluated artefact is a local-first Android workflow
  supporting capture/import, processing status, field review, history, receipt
  provenance and inventory. Local-first conformance is established by the frozen
  runtime/network manifest and observed data flow, not by the architecture label.
  (Sections 3.9-3.10 and 4.1, PDF pp. 64-65 and 71-76 /
  thesis pp. 64-65 and 71-76.)
- `THESIS_REQUIRED` - Fully local/cached mode sends no receipt-derived reference
  query outside the device boundary. Remote-reference mode must enumerate every
  transmitted receipt-derived category, destination, purpose, protocol,
  authentication and retention/cache behavior and narrows the local-first claim.
  Raw images and household records may be claimed local only after inspection.
  (Section 4.1 and Table 4.12, PDF pp. 76 and 109-110 /
  thesis pp. 76 and 109-110.)
- `THESIS_REQUIRED` - SQLite is the planned logical local persistence mechanism;
  the realized package, physical schema, migrations, foreign keys, indexes,
  backup/deletion behavior and transaction boundary must be frozen. (Section 4.1
  and Tables 4.11/4.13, PDF pp. 76, 106-108 and 111 /
  thesis pp. 76, 106-108 and 111.)
- `THESIS_REQUIRED` - PaddleOCR model/package, language, inference runtime,
  process/device and application bridge must be recorded. B2/B3/proposed behavior
  must remain compatible across the realized boundary. (Tables 4.1 and 4.13,
  PDF pp. 71-72 and 110-112 / thesis pp. 71-72 and 110-112.)
- `UNRESOLVED` - The thesis blueprint names a Flutter/Dart Android interface but
  explicitly classifies Flutter/Dart, OpenCV, Python and PyTorch as candidate
  technology roles whose realized use must be verified. It does not conclusively
  forbid Kotlin or select an on-device OCR integration. The project must choose
  and document the realized stack before implementation/freeze. (Section 3.8.1
  and Sections 4.1/4.6, PDF pp. 62-63, 71 and 110-112 /
  thesis pp. 62-63, 71 and 110-112.)
- `PROPOSED_DEVELOPMENT_CHOICE` - Use the shared immutable records plus versioned
  JSON/golden fixtures as the Python-to-Android conformance boundary. Validate
  token/source identity, B2 field output, B3-compatible candidate seeds, decisions
  and persistence eligibility on both runtimes before held-out evaluation.

## 15. Exact Task 2.3 deliverables and unresolved decisions

### 15.1 Task 2.3 deliverables

Task 2.3 should implement only the shared-interface foundation:

1. add `pipeline/proposed/contracts.py` containing the eight record groups from
   Section 12.3;
2. add `pipeline/proposed/__init__.py` without changing baseline behavior;
3. add `tests/test_proposed_contracts.py` with positive and negative invariant
   coverage;
4. add a synthetic B2-to-method/B3-compatibility fixture proving B2 value is
   permanent `c0` and a different generic result is only an altered candidate;
5. define language-neutral serialization fixtures and version/config references;
6. document the state machine and ownership boundary; and
7. leave scorer family, calibration method, numeric thresholds/resources and
   Android runtime unimplemented and explicitly `NOT_READY`.

`PROPOSED_DEVELOPMENT_CHOICE` - Completion requires tests for exactly-once
stored-gate consumption, permanent `c0`, provenance-preserving candidates,
rejected-candidate N/A semantics, feature-order/mask shape, score/probability
separation, immutable pre-review decisions, oracle/user mutual exclusion and
persistence eligibility.

### 15.2 Blockers before component implementation or evaluation

- `UNRESOLVED` - Source-gate executable minimum/threshold and fault policy beyond
  the specified state transitions. Blocks orchestration implementation.
- `UNRESOLVED` - Candidate normalization, edit similarity, displacement formula,
  limit/grid, validation objective and tie rule. Blocks candidate implementation.
- `UNRESOLVED` - Exact hard-constraint rule IDs, field grammars and tolerances.
  Blocks constraint implementation.
- `UNRESOLVED` - Final encoding/type/range for all seven feature slots and every
  missingness rule. Blocks feature/scorer implementation.
- `UNRESOLVED` - Scorer family, training objective, labels, hyperparameter grid
  and deterministic tie rule. Blocks scorer fitting.
- `UNRESOLVED` - Calibration method or justified bounded-probability identity,
  plus validation fitting details. Blocks probability-dependent policies.
- `UNRESOLVED` - Numeric replacement margin, acceptance threshold, conflict
  tolerance, PT1 coverage tolerance and their predeclared grids/tie rules. Blocks
  configuration selection.
- `UNRESOLVED` - Lawfully usable retailer, pantry terminology and Malaysian price
  resources, snapshot versioning and coverage. Blocks resource-enabled runs.
- `UNRESOLVED` - Frozen B2/B3 implementation/configuration hashes and
  cross-runtime fixtures. Blocks formal evaluation freeze.
- `UNRESOLVED` - Realized Android framework, OCR/process boundary, physical
  SQLite schema and security/network configuration. Blocks prototype freeze,
  not Task 2.3 Python contract work.

### 15.3 Non-blocking Task 2.3 choices

- `UNRESOLVED` - Exact serialization format and enum spelling may be selected in
  Task 2.3 if it preserves every thesis state and uses versioned fixtures.
- `UNRESOLVED` - Whether `CandidateEvidenceV1` embeds the vector or references an
  immutable vector record is a schema design choice.
- `UNRESOLVED` - Whether B3 compatibility uses an adapter over `B3Result` or a
  shared pure rule kernel may remain open if `c0` and conformance invariants are
  fixed.

## 16. Corrections to the Task 2.1 provisional audit

The thesis review makes these material corrections or refinements. Items 1-8 and
10 are `THESIS_REQUIRED`; item 9 combines a thesis-qualified candidate stack with
an `UNRESOLVED` realization choice. The item-specific references below span
PDF pp. 39-41, 58-60, 71-72, 82, 87, 91-93 and 95-96 /
thesis pp. 39-41, 58-60, 71-72, 82, 87, 91-93 and 95-96.

1. `c0` is now verified as the original B2-extracted method-ready value, not a
   B3-transformed value. (Section 4.3 and Algorithm line 3, PDF pp. 82 and 95 /
   thesis pp. 82 and 95.)
2. Generic normalization is a candidate source and must coexist with permanent
   `c0`; current `B3Result.receipt_output` therefore needs a proposed-method
   adapter before use in Algorithm 4.1. (Table 4.6, PDF p. 87 /
   thesis p. 87; adapter requirement is `PROPOSED_DEVELOPMENT_CHOICE`.)
3. `candidateLimit` placement is fixed: deduplicate and non-price rank first,
   apply the limit while retaining `c0`, then create candidate audit/constraints.
   (Section 4.3 and Algorithm lines 5-8, PDF pp. 82 and 95 /
   thesis pp. 82 and 95.)
4. Hard-constraint-rejected altered candidates must bypass feature construction,
   scoring and calibration while retaining an audit record. (Table 4.6,
   PDF p. 87 / thesis p. 87.)
5. Equation 4.1 fixes a seven-slot conceptual feature order, although exact
   encodings remain unresolved. (Section 4.3.2, PDF p. 92 / thesis p. 92.)
6. `Theta_A`, `Kappa`, `Phi`, PT1 and PT2 are distinct configuration objects with
   different ownership. (Section 4.3.2 and Table 4.13, PDF pp. 93 and 111-112 /
   thesis pp. 93 and 111-112.)
7. PT1 and PT2 have explicit and different validation-selection rules; they
   cannot share an intuitive or post-hoc threshold. (Section 3.7.1,
   PDF pp. 58-60 / thesis pp. 58-60.)
8. Field `AUTO_ACCEPTED` and receipt `AUTO_RESOLVED` are different levels of the
   state model. (Algorithm line 23 and `aggregateReceiptDisposition()`,
   PDF pp. 91 and 96 / thesis pp. 91 and 96.)
9. The thesis plans Flutter/Dart and SQLite roles but treats realized technology
   use as manifest-verified; Kotlin/on-device integration remains a project
   decision rather than an assumed thesis mandate. (Sections 4.1 and 4.6,
   PDF pp. 71-72 and 110-112 / thesis pp. 71-72 and 110-112.)
10. Tier A uses a frozen 60/20/20 grouped split, while line alignment is selected
    only on a training-derived protocol subset excluded from fitting. (Sections
    3.2.3 and 3.3, PDF pp. 39-41 / thesis pp. 39-41.)

## 17. Readiness decision

`PROPOSED_DEVELOPMENT_CHOICE` - Task 2.3 is **READY WITH EXPLICIT LIMITS**. It may
define and test shared immutable records and adapters, but it must encode unresolved
configuration values as versioned `NOT_READY`/unselected states and must not choose
numeric thresholds, model families, resources or deployment technology.

Independent Team A/Team B component coding is **NOT YET READY**. The safe split is
after Task 2.3 shared records, B2-as-`c0` adapter semantics and cross-lane fixtures
are independently reviewed and frozen for development.
