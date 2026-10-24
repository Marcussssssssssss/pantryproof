# PantryProof Offline Evaluation Protocol and Leakage Manifest Specification V0

Status: **PROVISIONAL / PENDING METHODOLOGY APPROVAL**

## 1. Document authority and version

This document translates the moderated FYP1 thesis evaluation methodology into
future executable requirements. It is a documentation specification only. It
does not freeze the methodology, approve a dataset, authenticate a manifest,
authorize held-out access, or show that any evaluation has run.

Document version: `0`.

The following authority labels are normative within this document:

- `THESIS_REQUIRED`: directly required by the moderated thesis. A future
  implementation must preserve the requirement unless a formally approved
  methodology amendment supersedes it.
- `REPOSITORY_VERIFIED`: observed in the repository at the Task 2.5F1
  checkpoint. Repository presence does not establish scientific validity or an
  evaluation freeze.
- `PROPOSED_SCHEMA`: a documentation-level interface or taxonomy proposed here
  to make the thesis requirement executable. It requires approval before code
  or data use.
- `PENDING_APPROVAL`: a choice that is not fixed by the thesis or approved
  shared interfaces. No implementation may silently choose it.
- `NOT_IMPLEMENTED`: a required or proposed producer, validator, or evaluator
  is absent.
- `NOT_SPECIFIED`: the authoritative sources do not define the value or rule;
  it must not be guessed.

Controlling evidence, in descending order for this specification, is:

1. the moderated thesis, especially Sections 3.2.3, 3.3, 3.5, 3.7-3.10,
   Tables 3.5-3.11, Sections 4.3-4.6, and Algorithm 4.1;
2. the thesis traceability specification;
3. approved shared runtime contracts and their recorded invariants;
4. provisional repository implementations and manifests as engineering
   evidence only; and
5. this proposed offline schema, which cannot override items 1-3.

The principal thesis locations used here are Sections 3.2-3.2.2 and Tables
3.1-3.3 (PDF pp. 33-38), Section 3.2.3 (pp. 38-39), Section 3.3 and Table 3.5
(pp. 40-41), Section 3.5 and Table 3.7 (pp. 47-48), Section 3.6 and Table 3.8
(pp. 48-50), Section 3.7 and Tables 3.9-3.11 (pp. 50-60), Section 3.8
(pp. 60-63), Sections 3.9-3.10 (pp. 64-65), Chapter 4 decision/constraint
definitions and Algorithm 4.1 (pp. 78-96), Table 4.7 (p. 97), Table 4.10
(p. 103), Section 4.5 (pp. 104-105), and Table 4.13 (pp. 111-112). Page
references identify the moderated PDF and do not imply approval of this
proposed schema.

The Task 2.5F0 read-only audit in the task history is an advisory input and is
not a repository artifact. Documentation completion must not be interpreted as
methodology approval or evaluation readiness.

## 2. Dataset and evaluation cohort identities

### 2.1 Tier A primary population

`THESIS_REQUIRED`: Tier A is the primary, bounded Malaysian grocery
receipt-transaction population. The independent grouping and bootstrap unit is
one receipt transaction; a field prediction is not an independent sample.
This specification does not claim that the corpus has been collected, approved,
annotated, or frozen, and assigns no actual dataset or participant identifiers.

The planned recruitment scope is approximately 400 to 600 consented Malaysian
grocery receipt transactions. This is a purposive, quota-guided coverage target
for retailer, branch where available, receipt length, print quality, and capture
condition diversity. It is not a statistically representative population
estimate, a nationwide retailer-prevalence estimate, or evidence that collection
is complete. The future corpus manifest and report must state the achieved
sample size, achieved retailer/capture diversity, every sparse or unfilled quota
cell, field availability, dataset-eligibility exclusions, and documented
recruitment limitations before performance is interpreted.

The future partition manifest must define one immutable related-record group for
every eligible receipt before partition assignment. A group must co-locate:

- the same transaction;
- exact and near-duplicate receipts;
- alternate captures of the same receipt;
- related transactions covered by the approved grouping policy; and
- every receipt from the same de-identified contributor.

After grouping, eligible Tier A groups are assigned 60% training, 20%
validation, and 20% held-out test. Assignment proportions apply to the approved
grouped split procedure, not independently to fields or images. No group member
may cross a partition.

Partition roles are fixed as follows:

| Partition | Permitted use | Prohibited use |
| --- | --- | --- |
| Training | Fit the shared extractor and declared trainable correction/scoring components. Supply a separate alignment-development subset. | No held-out or validation outcome may be used to redefine training resources or the alignment subset. |
| Training alignment-development subset | Freeze the common deterministic line matcher from frozen comparator predictions and masked human match labels. | Excluded from scorer and extractor fitting. It must not use validation or held-out predictions. |
| Validation | Permitted hyperparameter/configuration selection, calibration fitting where applicable, PT1 common-coverage selection, and PT2 operating-point selection under predeclared rules. | Must not select line alignment or use held-out outcomes. |
| Held-out test | Evaluation of the completely frozen systems and manifests only. | No fitting, threshold selection, resource refinement, rule changes, result selection, or retry-driven tuning. |

### 2.2 Retailer and branch analyses

`THESIS_REQUIRED`: an unseen-retailer cohort contains only retailers that
contribute no Tier A training receipts and no retailer-specific mapping to the
fitted system. Its eligibility rule and minimum descriptive coverage must be
frozen in the corpus manifest before outcome inspection. If achieved coverage
does not satisfy that rule, the analysis is descriptive or
`NOT_ASSESSABLE`; the cohort cannot be selected after results are known.

Branch-only hold-out is a separate branch-generalization analysis and must not
be relabelled as unseen-retailer performance. Primary, unseen-retailer, and
branch-generalization result sets must retain distinct cohort identifiers.

If any participant contributes multiple held-out receipts, the main
receipt-level bootstrap remains required and a participant-clustered bootstrap
sensitivity analysis is additionally required. The clustering identifier must
be de-identified and used only for approved grouping and uncertainty analysis.

### 2.3 Separate evidence tiers and benchmarks

| Population | Permitted claim boundary | Separation rule |
| --- | --- | --- |
| Tier A | Paired receipt extraction, pre-review automatic risk/coverage, and evaluation-only oracle-policy analysis. | Never pooled with Tier B or SROIE. Oracle values do not become production commits. |
| SROIE | Separate secondary OCR/KIE benchmark using only verified released labels and definitions, with frozen OCR/B2 and no SROIE fine-tuning. | Cannot support Malaysian pantry CIER, retailer, price-reference, selective-verification, or Tier B usability claims. |
| Tier B | Distinct formative human-interaction pilot covering actual Accept/Edit/Reject behavior, predefined task completion, standard SUS, and qualitative evidence. | Not an external receipt benchmark and not pooled into Tier A metric denominators. The thesis plans approximately six to eight consenting adults; no realized count or collection status is asserted here. |

Cross-tier aggregation is prohibited even when field names overlap. Every
evaluation record must carry one dataset tier and one cohort/partition identity.

## 3. Offline reference and annotation schema proposal

### 3.1 Seven-field reference scope

`THESIS_REQUIRED`: the primary common receipt-field schema contains:

1. store name;
2. purchase date;
3. receipt item description;
4. quantity;
5. unit price where receipt reference is available because it is printed or
   separately derivable under the prospectively frozen receipt-annotation rule;
6. line total; and
7. receipt total.

Receipt-level fields bind to the receipt. Item description, quantity, unit
price, and line total bind to one adjudicated purchased-line identity. Duplicate
descriptions remain separate line identities. Pantry-normalized product identity
is a separate semantic target and is excluded from primary common-schema
micro-F1 unless every compared system was prospectively required to emit an
equivalent output.

### 3.2 Proposed offline-only reference records

`PROPOSED_SCHEMA`: a future reference package should contain immutable records
equivalent to the following logical entities. Names and serialization remain
`PENDING_APPROVAL`.

| Logical record | Required content |
| --- | --- |
| `ReferenceReceiptV0` | dataset/tier, partition, cohort memberships, de-identified grouping key, receipt reference ID, annotation version, adjudication state, and ordered reference-line IDs |
| `ReferenceLineV0` | receipt reference ID, stable line ID, source order, purchased-line status, and links to its field references |
| `ReferenceFieldV0` | receipt ID, nullable line ID only for receipt-level fields, field role, literal/adjudicated value, comparison-normalized value, availability state, reference origin such as receipt-printed or rule-derived where applicable, derivation-rule reference when applicable, annotator/adjudication provenance, and reason when unavailable or pending |
| `PredictionReferenceLinkV0` | evaluated run/system ID, frozen prediction key, reference key, match mode, deterministic alignment evidence, and match/unmatch status |

Offline reference records must never be embedded in runtime `ReceiptOutput`,
candidate, evidence, decision, review, or persistence contracts. Runtime code
must not receive reference correctness, hidden-line existence, or evaluator
availability as an input.

### 3.3 Reference and comparison states

The following distinctions are mandatory:

| Condition | Reference state | Evaluation treatment |
| --- | --- | --- |
| Value is visibly printed and adjudicable | `REFERENCE_AVAILABLE` with receipt-printed origin | Eligible for comparison. |
| Unit price is not printed but is legitimately derivable solely from original receipt evidence under the prospectively approved annotation rule | `REFERENCE_AVAILABLE` with rule-derived origin and derivation provenance | Eligible for unit-price comparison exactly like a printed reference. The derivation policy is `PENDING_APPROVAL`. |
| Unit price is neither printed nor legitimately derivable under that frozen rule | `REFERENCE_UNAVAILABLE` with reason | Excluded only from unit-price truth-dependent metrics. Count and report the exclusion. |
| Another required value is genuinely not visibly present or not annotatable under the approved guideline | `REFERENCE_UNAVAILABLE` with reason | Excluded only from metrics requiring that truth. Count and report the exclusion. |
| Annotation cannot yet be resolved | `ADJUDICATION_PENDING` | Evaluation/configuration integrity block for affected metrics; not reference unavailable and not silently excluded. |
| Reference is available but system emits no prediction | Reference remains available | False negative, including missing, extraction-failed, parse-failed, or unmapped output. |
| Reference is available and prediction disagrees | Reference remains available | Incorrect prediction under the frozen comparison rule. |
| Purchased line exists in reference but system never detected it | Reference line and fields remain available | Unmatched false negatives; receipt exact-match failure; possible omission CIER. No synthetic runtime review/fallback state is created. |

`THESIS_REQUIRED`: system non-production never creates reference unavailability.
No exclusion reason may transform an available reference error into an omitted
denominator row.

Unit-price ground truth is the adjudicated receipt unit price, either visibly
printed or separately derivable from original receipt evidence under the frozen
annotation rule. The exact derivation equation, rounding rule, exception
handling, and derivability criteria are all `PENDING_APPROVAL`; this document
does not select or imply them. Optional external retailer/product market-price
evidence is a versioned contextual runtime resource and must never establish,
impute, or adjudicate receipt unit-price ground truth. Its absence is neither
missing unit-price ground truth nor evidence that a prediction is wrong. A
missing or incorrect prediction against any reference-available printed or
legitimately derived unit price remains in every applicable denominator even
when external price evidence is unavailable.

### 3.4 Independent double annotation and quality assurance

`THESIS_REQUIRED`: at least 15% of Tier A receipts must be independently double
annotated. The subset must be chosen through a documented stratified random draw
across retailer and available capture-quality strata before model predictions
become available. Two eligible annotators must independently label from the
original receipt evidence, with no access to each other's annotations or system
predictions before comparison.

Before annotation starts, the protocol must name either a third eligible
adjudicator or an ethics-approved consensus mechanism, together with a
deterministic escalation and reason-recording rule. No adjudication role or route
may be selected after disagreements are observed. Pre-adjudication reporting
must include:

- field-level exact agreement for every field;
- Cohen's kappa for categorical field-presence or availability decisions;
- a prospectively frozen character-similarity measure for textual fields,
  including its exact metric, preprocessing, range, and direction; and
- numeric absolute differences for numerical fields.

No unapproved character-similarity measure and no agreement result is selected
or asserted here. Every original annotation, disagreement, comparison, reason,
escalation, and adjudicated result must remain in the audit trail. Routine
second-person verification, where one person checks another's completed record,
is useful quality assurance but is not independent double annotation unless the
two labels were produced independently before comparison.

## 4. Prediction-to-reference alignment

### 4.1 Immutable prediction identities

Every evaluated field must preserve:

- system/run/configuration identity;
- dataset, partition, receipt transaction, and receipt prediction identity;
- item-row identity for item fields;
- field identity and field role;
- permanent original B2 value `c0` and its source links;
- frozen `pre_review_predicted_value` and field decision, if produced;
- frozen receipt disposition before reference access; and
- the exact output stage being evaluated.

Two records with the same text but different receipt, line, or field-role
identity are not the same prediction. Duplicate prediction keys are an
evaluation integrity failure, not an opportunity to deduplicate after seeing
truth.

### 4.2 Common deterministic line alignment

`THESIS_REQUIRED`: alignment is selected only on a dedicated Tier A training
alignment-development subset. Frozen comparator predictions generate alignment
examples; trained annotators label matched and unmatched pairs with system
identity masked. Those receipts are excluded from extractor/scorer fitting.

The shared matcher must apply these frozen steps:

1. normalize description strings with Unicode NFKC, case folding, trimming,
   and repeated-whitespace collapse;
2. retain punctuation that changes product identity or a numeric value;
3. pair exact normalized-description matches first;
4. for remaining items, use normalized Levenshtein distance under monotonic
   source order and permit a pair only when it is within the training-selected
   threshold;
5. select the threshold from a predeclared finite training-only grid by
   alignment F1, choosing the smaller threshold on an F1 tie;
6. for equal matching costs, prefer the smallest absolute order difference and
   then the earlier reference index;
7. preserve duplicate descriptions as separate records; and
8. prohibit split/merged many-to-one matches.

No numerical threshold, grid, or new normalization parameter is selected by
this document. Validation and held-out results cannot select or revise the
matcher. Matcher subset IDs, comparator versions, predictions, labels,
normalization, grid, selected value, and tie outcome must be frozen in the
manifest.

After alignment, unmatched predictions are false positives and unmatched
reference-available fields are false negatives. Exact value comparison uses the
approved common normalization: text as above, dates in one ISO representation,
and monetary values numerically in Malaysian ringgit after removal of currency
symbols and thousands separators. The exact executable parsers and
cross-runtime canonicalization remain approval/freeze items; malformed values
must not be silently repaired by the evaluator.

## 5. Runtime decision and evaluation state separation

The future evaluator must preserve this sequence:

1. B2 produces the original extracted field; that exact value becomes permanent
   `c0`.
2. B3 remains a fixed non-selective comparator. B3 transformations may seed the
   proposed candidate path but never replace `c0` by definition.
3. Candidate generation, limiting, hard constraints, seven-slot evidence,
   scoring, calibration, selection, and policy operate without ground truth.
4. The selected value, `pre_review_predicted_value`, automatic-commit permission,
   field decisions, and exactly one receipt pre-resolution disposition are
   frozen.
5. Only after the freeze may Tier A reference comparison occur.
6. Tier A oracle substitution may apply only to fields actually frozen as
   `REVIEW_REQUIRED`. It is evaluation-only, cannot create review
   retrospectively, cannot discover hidden omitted lines, and cannot repair
   `FAILED/PRE_RESOLUTION` or `FALLBACK_NO_UPDATE`.
7. Tier B actual user action separately records `USER_CONFIRMED`,
   `USER_MODIFIED`, or rejection after a real presented review.
8. A later persistence service may record `COMMITTED` only after a successful
   write, or `FAILED/INVENTORY_PERSISTENCE` after a failed attempt. Neither
   outcome overwrites the frozen pre-resolution disposition.

The four receipt-level pre-resolution states are `AUTO_RESOLVED`,
`REVIEW_REQUIRED`, `FALLBACK_NO_UPDATE`, and `FAILED/PRE_RESOLUTION`, with
system-known precedence failure, fallback, review, automatic. Hidden reference
content is never consulted in aggregation.

Automatic-commit permission is not proof of persistence. Tier A
`ORACLE_POLICY_RESOLVED` is not a user action and must never authorize or be
reported as a production `COMMITTED` transition.

## 6. Metric population and denominator contracts

### 6.1 Common rules

`THESIS_REQUIRED`: metrics begin only after the applicable prediction, decision,
automatic-commit status, and receipt disposition are frozen. Unless a row below
states otherwise:

- `eligible receipts` means the receipts fixed by the approved cohort and
  partition manifest before outcomes;
- reference-unavailable fields are excluded only from metrics that require
  their truth, and their counts/reasons are reported;
- a reference-available field with no prediction is an error, not an exclusion;
- system failures, fallbacks, unresolved reviews, hidden omissions, and
  persistence failures remain visible under their stated denominators;
- zero or empty denominators are `NOT_ESTIMABLE`, never numeric zero; and
- every reported value carries dataset tier, partition, cohort, system,
  configuration, frozen-state, numerator, denominator, event count, exclusion
  ledger version, and software version.

### 6.2 Thesis-defined metric contracts

| Metric | Input population and unit | Numerator / denominator or aggregation | Inclusion, exclusion, and frozen state | Tier and pending dependencies |
| --- | --- | --- | --- | --- |
| Micro-F1 | All aligned common-schema field instances over eligible receipts; unit of resampling is receipt | Pool TP, FP, FN, then compute precision, recall, and F1. Do not average per-receipt F1 as a substitute. | Seven fields; unit price is included when receipt truth is reference-available through either a printed value or the prospectively frozen derivation rule. Unmatched prediction = FP; available unmatched reference = FN. Frozen pre-review output. | Tier A RQ1. Requires approved reference schema, unit-price derivability policy, and frozen matcher. |
| Macro-F1 | Same field instances, grouped by field type | Arithmetic mean of field-type F1 values | Missing predictions remain FN. A field type with an empty estimable denominator is reported `NOT_ESTIMABLE`; whether a summary may average the remaining types is `PENDING_APPROVAL` and must be predeclared. | Tier A RQ1 supporting metric. |
| Receipt exact match | Each eligible receipt | Count receipts for which every required reference-available field is correct and matched / eligible receipts | Any incorrect or unmatched available field fails the receipt. Disposition stays unchanged. | Tier A RQ1 supporting metric. |
| Automatic CIER risk | Receipts with frozen system-side `AUTO_RESOLVED` | AUTO_RESOLVED receipts containing at least one adjudicated CIER / all AUTO_RESOLVED receipts | Hidden omitted purchased line stays in denominator and numerator when it meets the frozen omission rubric. Empty automatic population is `NOT_ESTIMABLE`. | Tier A pre-review RQ1. Requires approved CIER annotation/rubric. |
| Automatic coverage | All eligible receipts | Receipts with frozen system-side `AUTO_RESOLVED` / eligible receipts | Hidden truth does not change the disposition or denominator. | Tier A RQ1 and supporting RQ2. |
| Receipt-level review rate | All eligible receipts under one named configuration | Receipts with at least one applicable system-side pantry-relevant `REVIEW_REQUIRED` decision / eligible receipts | PT1 and PT2 rates are separate. Hidden omissions create no synthetic review. | Tier A PT1/RQ1 and PT2/RQ2; requires frozen configuration. |
| Unresolved/no-update rate | All eligible receipts | Receipts ending in `FALLBACK_NO_UPDATE` or unresolved `REVIEW_REQUIRED` / eligible receipts | Report fallback and unresolved-review components separately. Tier B rejection is separate. | Tier A RQ1/RQ2. |
| Pre-resolution failure rate | All eligible receipts | Frozen `FAILED/PRE_RESOLUTION` receipts / eligible receipts | Separate from review, fallback, rejection, and persistence failure. | System-side RQ1/RQ2 reporting. |
| Inventory-persistence failure rate | Attempted inventory transactions | `FAILED/INVENTORY_PERSISTENCE` attempts / all persistence attempts | Later event; does not alter disposition. Any all-eligible proportion is supplementary and separately labelled. | Tier B/application reporting, not a substitute RQ1/RQ2 denominator. |
| Oracle-assisted residual CIER | Receipts complete under the frozen automatic/oracle policy path | Complete-policy receipts containing at least one residual CIER / complete-policy receipts | Failure, fallback, or unresolved review prevents policy completion. Hidden omission remains residual CIER after completion freezes. | Tier A oracle-assisted RQ2 only. |
| Oracle-assisted policy completion | All eligible receipts | Receipts complete via automatic decisions plus eligible oracle substitutions for actual review fields / eligible receipts | Hidden lines do not change completion. No production persistence meaning. | Tier A RQ2. |
| Tier B realized completion/commitment | Participants' actual task receipts under the approved pilot script | Predeclared completed or committed end states / eligible Tier B task instances | Actual user action only; report rejection and persistence outcomes separately. | Tier B RQ3. Exact task eligibility/end states require the dated pilot script. |
| Field-level confirmation rate | System-side pantry-relevant decisions eligible for automatic acceptance or review | Decisions routed to `REVIEW_REQUIRED` / eligible field decisions | Hidden undetected fields are outside this workload denominator but remain FN/CIER evidence. Fallback/failure are separate. | Tier A PT2/RQ2; Tier B interaction reported separately. |
| Automatic correction attempt | Frozen field predictions with adjudicable truth | Event indicator: `pre_review_predicted_value != c0` | An unchanged incorrect `c0` is an extraction error, not an attempt. | Tier A pre-review RQ1. |
| Correction precision | Automatically committed correction attempts with adjudicable truth | Attempts where `c0` is wrong and altered frozen prediction is correct / attempts with `automatic_commit_status = PERMITTED` | Requires actual value change and frozen automatic permission. Empty denominator is `NOT_ESTIMABLE`. | Tier A pre-review RQ1. |
| Introduced-error rate | Same denominator as correction precision | Attempts where `c0` is correct and altered frozen prediction is wrong / same automatically committed, adjudicable attempts | Must share the exact denominator ledger with correction precision. | Tier A pre-review RQ1. |
| Net correction benefit | Same frozen event definitions | Successful automatic-correction count minus introduced-error count | Report both component counts; do not hide harm in the net. | Tier A pre-review RQ1. |
| ECE | Fields with frozen pre-review prediction, valid correctness probability, and adjudicable truth | Ten equal-width probability bins; weighted absolute confidence-accuracy gap under the approved implementation | Never fabricate probability for fallback, failure, constraint bypass, or a field that did not reach scoring. Report probability-availability coverage. | Tier A supporting calibration/RQ2. Exact bin-boundary convention and availability-coverage denominator are `PENDING_APPROVAL`. |
| Brier score | Same calibration-evaluable fields as ECE | Mean squared difference between calibrated correctness probability and observed correctness | Must use the same inclusion/exclusion ledger as ECE and report probability-availability coverage. | Tier A supporting calibration/RQ2. Availability-coverage denominator is `PENDING_APPROVAL`. |
| Risk-coverage reporting | Predeclared validation and held-out operating points | At each point report automatic CIER risk with automatic coverage and the associated review/fallback/failure evidence | No post-hoc point deletion or smoothing. No AUC is required or defined by the thesis. | Tier A RQ1/RQ2. Exact plotting/interpolation summary beyond points is `NOT_SPECIFIED`. |
| System-only processing latency | Each run in the prospectively frozen latency protocol | Primary statistic is median elapsed time from image submission to review screen or automatically accepted output | Excludes human decision time. Freeze receipt set, repetitions, warm-up, cold/warm definition, cache/resource state, timestamps, failure/fallback treatment, and any tail statistic before measurement. | RQ3. PT3 is the project-defined target of median below 3 seconds on the selected device. |
| Tier B task completion | Each predefined participant-task instance | Tasks reaching the scripted end state without facilitator execution / eligible task instances | Fixed task order; assistance logged. Descriptive only. | Tier B RQ3. |
| SUS | Completed standard ten-item SUS instruments under the pilot protocol | Standard SUS scoring; report descriptively with task completion and qualitative evidence | Custom questions are separate and never included in SUS. | Tier B RQ3. PT4 is the descriptive target mean at least 70; no population inference. |

Price-reference coverage and missingness are required supporting reports, but
the thesis does not fix their exact denominator. A denominator such as eligible
item-price evidence opportunities must be defined and approved before use; it
must never be substituted for receipt unit-price ground-truth availability,
whether that truth was printed or legitimately derived under the frozen
annotation rule. Missing external evidence cannot exclude a reference-available
unit-price prediction error.

### 6.3 Uncertainty and paired comparison

`THESIS_REQUIRED`: use 2,000 paired receipt-level bootstrap resamples and
percentile 95% confidence intervals. Each replicate samples receipt transactions
with replacement and uses the same sampled receipt identifiers for PantryProof
and its paired comparator. For the primary micro-F1 difference, recompute pooled
TP, FP, and FN for each system, recompute each micro-F1, and record PantryProof
minus B3. The percentile interval is formed from the 2,000 paired differences.
Per-receipt F1 averaging is not a replacement.

Critical-event reporting includes event counts and interval widths; no minimum
event count is fabricated. If contributors repeat in held-out data, report the
participant-clustered bootstrap sensitivity result in addition to the main
receipt-level result. Any stochastic component introduced later requires a
prospective seed/aggregation amendment before held-out access.

### 6.4 PT1, PT2, and objective classifications

`THESIS_REQUIRED`:

- The general four-way objective vocabulary is: `ACHIEVED` when all required
  evidence and predefined criteria are satisfied; `NOT_ASSESSABLE` when a
  mandatory evaluation cannot validly execute or required decision evidence is
  unavailable; `PARTIALLY_ACHIEVED` only when the objective-specific rule
  permits it and all mandatory components are assessable but only some pass;
  and `NOT_ACHIEVED` when all mandatory components are validly assessable but
  the predefined criteria are not met. Objective-specific PT1/PT2 rules below
  refine this vocabulary and cannot be changed after outcomes are observed.

- The primary field-extraction comparison is paired PantryProof versus B3
  common-schema micro-F1. Confirmed improvement requires a positive difference
  whose receipt-level bootstrap 95% interval excludes no improvement. B1 and B2
  remain mandatory supporting comparisons.
- PT1 separately requires at least 20% relative automatic-CIER-risk reduction
  versus B3 at the validation-selected common-coverage point within the
  predeclared tolerance, with paired risk intervals excluding no improvement.
  No valid common-coverage pair is `NOT_ASSESSABLE`. If a valid pair has B3 risk
  zero, the relative component and RO2 are `NOT_ASSESSABLE`; report no invented
  percentage, but retain absolute difference, event counts, uncertainty, and
  the separate field result. With a valid nonzero baseline, failure of the
  criterion is `NOT_ACHIEVED`. `PARTIALLY_ACHIEVED` applies to RO2 only when
  both mandatory components are assessable and exactly one meets its criterion.
- PT2 considers only predeclared validation operating points. Select the point
  with the lowest field-level confirmation rate whose upper 95% bootstrap bound
  for Tier A oracle-assisted residual CIER does not exceed B3 automatic
  validation CIER under B3's fixed non-selective semantics. If none qualifies,
  freeze `NO_VALID_POINT`, classify PT2 `NOT_ASSESSABLE`, and apply no PT2
  threshold to held-out RQ2.
- RO3 is `ACHIEVED` only when a valid PT2 point is validation-frozen, held-out
  policy evaluation executes validly, and all required RQ2 outputs are produced.
  It is `NOT_ASSESSABLE` for `NO_VALID_POINT` or missing mandatory valid
  calibration/policy/evaluation evidence. It is `NOT_ACHIEVED` only when an
  explicitly mandatory requirement executes validly and is not satisfied.
  `PARTIALLY_ACHIEVED` is not used for RO3.

The common-coverage tolerance, operating grids, tie rules beyond those already
stated by the thesis, and all realized values remain `NOT_SPECIFIED` here.

### 6.5 CF1 and RR1 conformance/reporting contracts

`THESIS_REQUIRED`: CF1 assesses observed runtime data-flow conformance against
the prospectively approved and frozen local-first boundary. It is a conformance
criterion, not a new numerical score. The evaluated manifest must identify the
actual process/device location and data categories for receipt images, OCR text,
source crops, structured fields, household records, persistence, and optional
reference access. No conformity result is asserted by this document.

If an external reference lookup transmits receipt-derived information, the
report must disclose the exact outgoing categories, such as the actual
retailer/product identifier, text fragment, hash, or other field sent, together
with purpose, destination, protocol/authentication, response categories, and
missing/timeout behavior. The local-first claim must be narrowed to the observed
boundary. Architectural conformance evidence is not formal privacy, security,
legal, or regulatory certification.

RR1 is required regardless of target attainment. It must report extraction;
automatic risk and coverage; review, fallback, unresolved, and completion;
successful and harmful correction; calibration and probability availability;
retailer/cohort analysis; pre-resolution failures; and later
inventory-persistence failures under their separate frozen denominators. No
category may be omitted because its result is unfavorable or unavailable.

## 7. Leakage and configuration freeze manifest

### 7.1 Proposed manifest envelope

`PROPOSED_SCHEMA`: one versioned evaluation freeze manifest should be approved
before held-out access. It should contain:

| Block | Required fields |
| --- | --- |
| Authority | manifest ID/version, status, creation/freeze timestamps, approving roles, approval references, amendment lineage, evaluated repository revision |
| Dataset | tier/dataset ID, planned and achieved corpus size, achieved retailer/capture diversity, sparse/unfilled quota cells, field availability, exclusions, recruitment limitations, corpus/annotation versions, consent/license/governance references, eligibility rules, partition IDs, cohort definitions, and source-label lineage |
| Annotation QA | independent-double-annotation subset and draw record, retailer/capture-quality strata, selection timestamp relative to model predictions, eligible annotator/adjudicator roles, frozen escalation route, exact-agreement and kappa specification, approved textual-similarity specification, numeric-difference specification, disagreement/adjudication audit location, and QA status |
| Grouping | transaction group, duplicate/near-duplicate group, alternate-capture group, related-record group, de-identified contributor cluster, grouping algorithm/policy version, and cross-partition validation result |
| Alignment | training-only subset ID, excluded-from-fitting evidence, comparator versions/predictions, masked match labels, normalization version, threshold grid, selected threshold, tie result, and approval reference |
| Runtime/baselines | preprocessing, OCR package/model/runtime, B1/B2/B3 implementation/configuration versions, B2 training/selection route, decoding and missing/ambiguous behavior |
| Proposed method | candidate-generation, normalization, deduplication, ranking, candidate-limit, provenance, hard-rule profile, feature schema/order/missingness, scorer/model/training, replacement, and selection versions |
| Configurations | separate immutable `Theta_A`, `Kappa`, `Phi`, PT1, and PT2 identities, versions, states, selection grids/criteria/ties, validation evidence, and `NO_VALID_POINT` where applicable |
| Resources | retailer, terminology, and price/reference snapshot IDs, providers/sources, date/version, licensing/approval, cache/update policy, lookup coverage scope, and exact lineage from permitted pre-existing or training-only material |
| Software/environment | evaluation software version, interpreter/framework/package versions actually used, device/OS/build, process/device locations, deterministic settings, seed list where applicable, and output schema version |
| Freeze evidence | declared digests with algorithm/scope, independent verification status, verifier/registry/reference, verification timestamp, cross-runtime fixture status, and unresolved items |
| Execution | run ID, partition role, input/output locations, start/end time, run status, exclusion-ledger version, and proof that the runner opened only the authorized partition role |

Every configurable setting must be classified as deterministic-before-validation,
training-fitted, validation-selected, or evaluation-only. Held-out-derived is
never a permitted source.

### 7.2 Digest and authentication boundary

A nonempty hash string proves only that a string was recorded. The manifest
must distinguish:

- `DECLARED_DIGEST`: algorithm, scope, and value are present but bytes have not
  been independently authenticated;
- `VERIFIED_DIGEST`: a named approved verifier or trusted registry has checked
  the declared bytes and recorded evidence; and
- `UNAVAILABLE`: no authentic digest evidence exists.

No digest, signature, timestamp, approval reference, dataset ID, or resource
snapshot may be fabricated. Current V1 `content_hash` validation is structural
only. Current B1/B2/B3 manifests are provisional and explicitly not held-out
evaluation-frozen; their null hash fields cannot satisfy this section.

### 7.3 Leakage assertions

Before an evaluation run, automated and human review must establish that:

- related-record and contributor groups do not cross partitions;
- alignment examples come only from the training alignment subset and those
  receipts are excluded from extractor/scorer fitting;
- retailer, terminology, price/reference mappings, and running statistics do
  not contain validation or held-out outcomes except where the thesis expressly
  permits validation fitting/selection;
- scorer training uses training data only;
- calibration fitting, when applicable, uses validation predictions from the
  frozen scorer;
- PT1 and PT2 selection use validation only and remain distinct;
- no ground truth, held-out annotation, evaluator match, or CIER label enters a
  runtime record or pipeline input; and
- any post-inspection material method/configuration change creates a new
  version and requires the affected experiment to be repeated under an approved
  amended plan.

### 7.4 Ethics, privacy, and research export boundary

`THESIS_REQUIRED`: Tier A collection and Tier B participant use may begin only
after applicable ethics approval and informed consent are documented.
Participation must remain voluntary, and approved withdrawal and retention
conditions must be recorded and followed. This document does not claim that an
approval, consent form, participant record, or dataset currently exists.

Research export must be a separately controlled, data-minimized boundary. It may
contain only the minimum receipt regions, structured fields, and pilot logs
permitted for the approved annotation/evaluation purpose. Before export,
payment references, loyalty identifiers, QR codes, barcodes, card traces, phone
numbers, and other personal text must be masked and manually verified. The
export record must retain the applicable consent/approval reference, approved
purpose, included data categories, manual-check evidence, recipient/access
scope, retention period, withdrawal handling, and deletion boundary. Raw images
and identifiable pantry records remain on-device by default unless an approved,
explicitly documented boundary states otherwise.

## 8. Exclusion and reason ledger

### 8.1 Proposed typed ledger

`PROPOSED_SCHEMA`: every skipped, unavailable, failed, unresolved, or
non-assessable unit must produce an offline-only ledger entry containing a
ledger ID, dataset/tier/partition, run/system/configuration, receipt and optional
line/field key, stage, typed category, reason code/detail, affected metrics,
denominator action, provenance reference, and timestamp/software version.

| Category | Meaning | Permitted metric effect |
| --- | --- | --- |
| `DATASET_LEVEL_EXCLUSION` | Receipt was prospectively ineligible under the frozen corpus rule | Exclude from eligible population only when the pre-outcome rule and reason are recorded. Never create after seeing performance. |
| `REFERENCE_LABEL_UNAVAILABLE` | A non-unit-price value is genuinely not visible/annotatable, or a unit price is neither printed nor legitimately derivable under the frozen annotation rule | Exclude only from truth-dependent field/event metrics. Report count/reason. A printed or legitimately derived unit price is reference-available and cannot use this exclusion. Does not alter runtime disposition. |
| `ADJUDICATION_PENDING` | Reference is unresolved, not proven unavailable | Block affected evaluation until resolved or an approved protocol amendment says otherwise. |
| `SYSTEM_MISSING_PREDICTION` | Reference is available but system produced no comparable value | Include as FN and receipt exact-match failure; may support omission CIER. Never an exclusion. |
| `SYSTEM_FAILURE` | Pre-resolution or execution failure | Retain in eligible receipt denominators and the typed failure rate. Any unavailable field predictions are handled according to the frozen metric contract, not removed wholesale. |
| `REVIEW_WITHOUT_RESOLUTION` | Actual `REVIEW_REQUIRED` lacks an eligible oracle/user resolution for the relevant path | Count as unresolved review; prevents Tier A policy completion when applicable; never invent a resolution. |
| `CALIBRATION_OR_PROBABILITY_UNAVAILABLE` | Applicable candidate/field lacks a required valid probability | Preserve unavailable reason, c0/review behavior under Algorithm 4.1, and probability-availability reporting. Do not fabricate a probability. |
| `OPTIONAL_EXTERNAL_REFERENCE_UNAVAILABLE` | Retailer/terminology/price resource was unavailable where optional | Preserve feature/resource missingness and coverage. It is not negative ground truth and, by itself, neither review nor fallback. |
| `METRIC_NOT_ASSESSABLE` | Frozen metric/objective denominator or mandatory evidence cannot validly be produced | Report `NOT_ESTIMABLE` for an empty metric denominator and the thesis-defined `NOT_ASSESSABLE` for an objective/policy decision, with reason. Never replace with zero. |
| `CONFIGURATION_OR_FREEZE_FAILURE` | Required configuration, manifest, approval, hash verification, or partition control is invalid/missing | Block the affected run or metric. Do not downgrade to ordinary candidate missingness or select an alternative after held-out inspection. |

`PENDING_APPROVAL`: exact enum spellings, subreason catalogue, and serialization.
Regardless of those choices, no ledger entry may silently remove a
reference-available error from a denominator. Until the exact unit-price
derivability policy is approved and frozen, the evaluator must not manufacture a
derived reference or use external market-price evidence as a substitute.

## 9. Contract V1/V2 dependency mapping

| Evaluation need | Current repository evidence | Availability and boundary |
| --- | --- | --- |
| Original OCR/source and B2 receipt | Contract V0 `ReceiptSourceEvidence`, `OcrSourceToken`, `StructuredField`, `ReceiptItemRow`, `ReceiptOutput` | `REPOSITORY_VERIFIED`. Runtime source only; no ground truth. `ReceiptOutput` is pre-review automatic. |
| Permanent `c0` | `MethodReadyFieldV1` and B2-to-proposed adapter | `REPOSITORY_VERIFIED`. Exact extracted B2 value and sufficient stored gate are bound. |
| B3 comparator/seed relationship | frozen B3 implementation, provisional manifest, `B3CompatibleSeedV1` | Comparator and adapter evidence exist, but B3 manifest is not held-out frozen and a seed is not a replacement for c0. |
| Candidate set/provenance/limit | Candidate generation, deduplication, identity, provenance, ranking, limiting, and finalization modules; `CandidateRecordV1` | `REPOSITORY_VERIFIED` synthetic/provisional producers exist through retained-set finalization. No accuracy/evaluation claim. |
| Hard-constraint inputs | hard-constraint context and operand-audit modules | `REPOSITORY_VERIFIED` observational inputs only. No approved semantic hard-rule evaluator. |
| Constraint result | V1 `ConstraintResultV1` has only eligible/rejected; V2 proposal adds unavailable states | V1 type exists but no approved producer. It cannot faithfully represent mandatory constraint unavailability. V2 is proposal only. |
| Seven-slot raw inputs | E1 `FeatureInputReadinessResultV0` | `REPOSITORY_VERIFIED` observation only. It explicitly produces no features, eligibility, scores, probabilities, or decisions. |
| Candidate evidence, raw score, calibrated probability | V1 `CandidateEvidenceV1` | Constructor exists; production feature/scorer/calibrator producers are `NOT_IMPLEMENTED`. Rejected candidates bypass scoring. |
| Frozen field decision | V1 `FieldDecisionV1` | Constructor exists; selector/policy producer is `NOT_IMPLEMENTED`. Unavailable selected probability requires c0/review semantics. |
| Frozen receipt disposition | Contract V0 `PreResolutionDisposition` | Structural record exists. Future orchestrator completeness/aggregation producer is `NOT_IMPLEMENTED`. |
| Tier A oracle or Tier B user resolution | V1 `ReviewResolutionV1` | Structural record exists with actor/event provenance. No actual oracle-policy or user-event producer is implemented. Oracle/user meanings must remain distinct. |
| Final persistence outcome | V1 `FinalApplicationOutcomeV1` and Contract V0 persistence boundary | Structural validation exists; no SQLite write service or transaction evidence producer is implemented. |
| Offline reference, alignment, metric, bootstrap, exclusion, and freeze records | None of the runtime contracts | `NOT_IMPLEMENTED`; must remain offline and versioned rather than adding truth to runtime contracts. |

Contract V1 is a provisional development interface, not evaluation-frozen.
The coordinated hard-constraint Contract V2 remains `PENDING SHARED APPROVAL`.
All HC-D01 through HC-D13 decisions remain pending, including architecture,
precedence, zero-applicable rules, c0 routing, rule catalogue, arithmetic policy,
authentication, optional-rule effect, downstream versioning, serialization,
resource scope, and the field-wide effect of a nonselected unavailable altered
candidate. This specification does not project `CONSTRAINT_UNAVAILABLE` into
V1, fabricate `ELIGIBLE`, or decide HC-D13.

## 10. Proposed future synthetic conformance tests

No tests are implemented by this document. Future synthetic-only tests should
cover at least:

| Case | Required assertion |
| --- | --- |
| Held-out leakage into a retailer/terminology/price snapshot | Manifest validation rejects the run and records `CONFIGURATION_OR_FREEZE_FAILURE`. |
| Validation or held-out receipt used for matcher development | Reject before metric computation. |
| Same transaction, near duplicate, alternate capture, related record, or contributor split across partitions | Grouping validation rejects the partition manifest. |
| Prediction and reference from different tiers pooled in one metric | Reject; Tier A, Tier B, and SROIE outputs remain separate. |
| Duplicate receipt/line/field prediction key | Reject before alignment or scoring; do not deduplicate against truth. |
| Available reference with missing prediction | Count FN and exact-match failure; ledger entry cannot exclude it. |
| Completely undetected purchased line | Count unmatched reference fields/FN and possible omission CIER without creating runtime review/fallback. |
| Printed unit-price truth with missing or incorrect prediction | Keep the unit-price field in every applicable denominator; score the missing value as FN or the mismatch as incorrect. |
| Unit price legitimately derived under the frozen annotation rule, with missing or incorrect prediction | Treat it as reference-available exactly like printed truth and retain derivation provenance. |
| Claimed derived unit price without an approved frozen derivability policy | Reject/block the affected annotation/evaluation; do not guess a formula or relabel it available. |
| External market-price lookup offered as unit-price ground truth | Reject the reference construction; external plausibility evidence cannot establish receipt truth. |
| Genuinely unavailable unit-price truth because it is neither printed nor derivable under the frozen rule | Exclude only the unit-price truth-dependent comparison and report it; retain the receipt for other fields. |
| Optional external price evidence unavailable | Preserve missing optional evidence; do not relabel unit-price truth, candidate correctness, hard failure, or review. |
| Available unit-price truth but optional price lookup missing | Score the prediction against receipt truth; optional-resource absence cannot remove the error. |
| Independent double-annotation subset below 15%, selected after model predictions, or not stratified as required | Reject annotation-QA conformance; do not fabricate agreement evidence. |
| Annotators saw each other's labels or system predictions before comparison | Reject the affected independent-double-annotation claim and retain the audit finding. |
| Ordinary second-person verification labelled independent double annotation | Reject the classification unless two independent pre-comparison labels exist. |
| Missing preselected adjudicator/consensus route or unapproved textual agreement metric | Block annotation-QA approval; do not select the mechanism after disagreements. |
| Agreement report lacks pre-adjudication exact agreement, categorical kappa, textual similarity, numeric absolute differences, or disagreement trail | Reject incomplete QA reporting. |
| Achieved Tier A size/diversity or sparse quota cells omitted from manifest | Reject corpus-manifest completeness; planned 400-600 target cannot substitute for achieved evidence. |
| Reference adjudication pending | Block affected metric; do not coerce to unavailable or incorrect. |
| Mandatory hard-constraint evidence unavailable | Prevent feature/scoring execution and preserve audited unavailability. Aggregate/controller expectation is `PENDING_APPROVAL` under HC-D01-HC-D13. |
| Rejected or unavailable c0 | Preserve permanent c0 and prohibit automatic commitment. Exact route is `PENDING_APPROVAL` under HC-D04/HC-D05. |
| Nonselected altered candidate constraint unavailable | Preserve candidate audit; field-wide commit/review expectation is `PENDING_APPROVAL` under HC-D13. |
| Required probability unavailable after otherwise valid probability-dependent setup | Freeze original c0, set automatic commitment not permitted, and route actual review under Algorithm 4.1 line 16; do not treat as configuration-level invalidity. |
| Invalid probability-dependent configuration | Block applicable held-out execution as configuration/freeze failure; do not reuse the line-16 runtime fallback. |
| Review-required field without eligible oracle resolution | Tier A policy remains incomplete; no oracle value is invented. |
| Review-required field without actual Tier B action | No user resolution, completion, commitment, or persistence attempt is fabricated. |
| Oracle resolution supplied for auto-accepted/failed/fallback field | Reject; oracle applies only to actual frozen review. |
| Oracle result presented as production commit | Reject tier/state transition. |
| Persistence failure after frozen automatic/review outcome | Preserve original disposition and count failure only in attempted persistence denominator. |
| Mutation of c0, pre-review prediction, disposition, or configuration after reference access | Reject reconstruction/run; require a new approved version and rerun. |
| Micro-F1 implementation averages receipt F1 | Reject conformance; pooled TP/FP/FN is required. |
| Empty metric denominator | Return `NOT_ESTIMABLE` with reason, never zero. |
| PT1 with no common-coverage pair or B3 risk zero | Produce the thesis-required `NOT_ASSESSABLE` branch and retain supporting evidence. |
| PT2 with no admissible validation point | Freeze `NO_VALID_POINT`; no held-out PT2 threshold. |
| Bootstrap samples differ between paired systems | Reject paired interval computation. |
| Manifest contains a hash string without verification evidence | Classify as declared, not authenticated. |
| Tier A collection or Tier B participation lacks documented applicable ethics approval or informed consent | Block collection/use authorization; do not infer approval. |
| Research export contains unmasked payment, loyalty, QR/barcode, card, phone, or other personal text, or lacks manual-check evidence | Reject the export boundary and record the governance failure. |
| External reference lookup transmits an undisclosed receipt-derived category | CF1 cannot be established; disclose the exact observed category and narrow the local-first claim. |
| CF1 reported as a numeric privacy/certification score | Reject the report; CF1 is observed architectural data-flow conformance, not formal certification. |
| RR1 omits an applicable unfavorable or unavailable reporting family | Reject required-reporting conformance; preserve each family's separate denominator. |

Synthetic conformance verifies record and denominator behavior only. It cannot
establish extraction accuracy, calibrated probability validity, dataset
representativeness, consent, or held-out performance.

## 11. Approval and implementation dependencies

### 11.1 Ownership and coordination

| Decision/work item | Primary owner | Required coordination |
| --- | --- | --- |
| Candidate/reference feature, scorer, calibration, and correction-policy methodology | Leng | Shared-contract review; no held-out access before method freeze. |
| B2/B3 output keys, missing/unresolved behavior, line/item associations, comparator manifests, and evaluation adapter evidence | Tai | Leng confirms proposed-method consumption; shared review for interface changes. |
| Offline reference schema, annotation guideline, CIER labels, grouping, and baseline-fair comparison | Joint methodology/data work | Tai extraction/evaluation evidence plus Leng method requirements; data-governance approval. |
| Contract V2, HC-D01-HC-D13, orchestration, cross-runtime serialization, and persistence boundary | Shared owners | Explicit Leng/Tai/methodology/Android approval as applicable. |
| Tier A/Tier B collection, consent, retention, export, and held-out authorization | Data-governance/ethics owners | Recorded institutional approval and approved participant materials. |

Leng can independently prepare synthetic, offline evaluator designs that do not
resolve shared semantics, use datasets, or alter Tai-owned components. Leng
cannot independently authenticate B2/B3, approve Contract V2, define Tai's
association semantics, authorize data use, or select held-out-facing policies.

### 11.2 Required gates

1. **Design review** - approve this document's source interpretation and mark
   every `PENDING_APPROVAL` item as accepted, amended, or deferred.
2. **Schema approval** - approve offline reference, alignment, metric result,
   exclusion-ledger, and freeze-manifest schemas without adding truth to runtime
   contracts.
3. **Shared-method approval** - resolve all HC decisions required by the
   evaluator path, approve V2 or an equally expressive boundary, and approve
   c0/controller behavior.
4. **Synthetic implementation authorization** - separately authorize code and
   synthetic conformance tests. This document does not grant it.
5. **Tai interface confirmation** - freeze the B2/B3 output and comparator
   manifests, identities, missing states, and line associations consumed by the
   evaluator.
6. **Data-governance approval** - confirm ethics, consent, licensing, access,
   de-identification, retention, and tier-specific use before any dataset access.
7. **Training/validation freeze** - freeze alignment, resources, learned
   components, calibration, PT1, PT2, configurations, software, and verified
   manifests using training/validation only.
8. **Held-out execution authorization** - permit one evaluation-only run after
   an independent leakage/readiness audit. Documentation or placeholder records
   alone cannot satisfy this gate.

## 12. Future execution readiness checklist

Every item below is intentionally unchecked.

- [ ] Methodology reviewers approve this protocol and all retained pending
  choices needed by the intended run.
- [ ] Tier A corpus identity, eligibility rule, annotation version, and lawful
  use are recorded without exposing participant identity.
- [ ] The approximately 400-600 transaction target remains identified as
  purposive and quota-guided; the manifest reports achieved sample size,
  retailer/capture diversity, sparse or unfilled quota cells, field
  availability, exclusions, and recruitment limitations without claiming
  statistical representativeness or completed collection.
- [ ] Transaction/duplicate/alternate-capture/related-record/contributor groups
  are frozen and independently checked for partition leakage.
- [ ] The 60/20/20 grouped partition manifest is frozen; held-out access is
  technically and procedurally restricted.
- [ ] Unseen-retailer eligibility/coverage and branch-generalization cohorts are
  frozen before performance inspection.
- [ ] Seven-field annotation guidelines, CIER rubric, and unavailable/pending
  states are approved; unit-price truth distinguishes receipt-printed,
  legitimately rule-derived, and unavailable values, and its exact derivation
  equation, rounding, exceptions, and criteria are prospectively frozen.
- [ ] At least 15% of Tier A receipts are selected before model predictions by
  the documented retailer/capture-quality stratified random draw, independently
  labelled by two eligible blinded annotators, and governed by the preselected
  adjudicator or ethics-approved deterministic consensus route.
- [ ] Annotation QA reports pre-adjudication field exact agreement, categorical
  presence/availability Cohen's kappa, the prospectively frozen textual
  character-similarity measure, numeric absolute differences, and the complete
  disagreement/adjudication audit trail; ordinary verification is not counted
  as independent double annotation.
- [ ] Offline reference records pass identity, uniqueness, type, visibility,
  line-link, and adjudication-completeness validation.
- [ ] The training-only alignment-development subset, predictions, masked
  labels, normalization, grid, selected matcher, and tie evidence are frozen;
  its receipts are excluded from extractor/scorer fitting.
- [ ] OCR, preprocessing, B1, B2, and B3 implementations/configurations are
  frozen with verified versions and approved comparator semantics.
- [ ] B2/B3 interfaces and permanent c0 semantics are confirmed by Tai and the
  shared reviewers.
- [ ] Candidate generation, hard constraints, feature schema, scorer,
  calibration, selection, and policy producers exist and pass synthetic
  conformance without ground-truth inputs.
- [ ] HC-D01 through HC-D13 are resolved wherever required; approved Contract
  V2 or an equally expressive audited boundary is implemented cross-runtime.
- [ ] `Theta_A`, `Kappa`, `Phi`, PT1, and PT2 are distinct, validation-frozen,
  authenticated references with complete selection evidence.
- [ ] PT2 records either a valid selected operating point or
  `NO_VALID_POINT`; no held-out threshold can be selected.
- [ ] Retailer, terminology, and price/reference snapshots have approved
  provenance, licensing, versioning, coverage scope, and verified digests.
- [ ] External market-price evidence remains optional contextual plausibility
  evidence and cannot create or adjudicate receipt unit-price ground truth or
  remove a reference-available unit-price error from a denominator.
- [ ] The evaluation runner enforces one authorized partition role at a time,
  immutable annotations, duplicate-key rejection, finite values, class/feature
  order, and deterministic output validation.
- [ ] Metric populations, empty-denominator behavior, ECE bin boundaries,
  probability-availability coverage denominator, risk-coverage presentation,
  and price-coverage denominator are approved and frozen.
- [ ] The 2,000 paired receipt-level bootstrap and participant-clustered
  sensitivity path pass deterministic synthetic tests.
- [ ] Exclusion/reason ledger validation proves that reference-available errors
  cannot disappear from denominators.
- [ ] Tier A automatic, Tier A oracle, Tier B user, and persistence outputs are
  stored and reported separately.
- [ ] The latency protocol freezes device, receipt set, repetitions, warm/cold
  state, cache/resources, timestamps, failure/fallback treatment, and tail
  statistic before measurement.
- [ ] The Tier B task script, end-state checklist, assistance log, unchanged
  ten-item SUS, qualitative codebook, consent, and pilot authorization exist.
- [ ] Applicable ethics approval and informed consent are documented before
  Tier A collection or Tier B participation, with approved voluntary
  withdrawal, retention, access, and data-minimization boundaries.
- [ ] Every research export masks and manually verifies payment references,
  loyalty identifiers, QR codes, barcodes, card traces, phone numbers, and
  other personal text, and records its approved purpose, categories, access,
  retention, withdrawal, and deletion evidence.
- [ ] CF1 is assessed only from observed data flow against the frozen local-first
  boundary; every externally transmitted receipt-derived category is disclosed,
  the claim is narrowed where necessary, and no formal privacy/regulatory
  certification is inferred.
- [ ] RR1 reports extraction, automatic risk/coverage,
  review/fallback/completion, harmful correction, calibration, retailer
  analysis, pre-resolution failure, and persistence failure under their
  separate denominators regardless of target attainment.
- [ ] Manifest digests are independently verified; no declared hash is treated
  as authenticated without evidence.
- [ ] An independent pre-run audit confirms no hidden ground truth, held-out
  tuning, cross-tier pooling, or unapproved post-freeze change.
- [ ] Held-out execution is explicitly authorized after every applicable item
  above is complete.

Until these conditions are met, the repository is not ready for held-out
evaluation. The safe next phase after approval of this document is a separately
authorized, synthetic-only design/implementation of the offline manifest and
ledger schemas; it must not access datasets or compute metrics.
