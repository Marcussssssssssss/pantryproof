# PantryProof Evaluation Workstream Decision Log

Log status: `CANONICAL_FOR_EVALUATION_WORKSTREAM_DECISIONS`

Recorded design status: `DESIGN_APPROVED_FOR_SYNTHETIC_IMPLEMENTATION`

Implementation status: `IMPLEMENTATION_NOT_YET_ACCEPTED`

Current task implementation authorization: `NOT AUTHORIZED IN THIS TASK`

Evaluation status: `NOT EVALUATION_FROZEN`

## 1. Purpose and scope

This file is the canonical decision log for PantryProof's offline evaluation
workstream. It records evaluation-schema, validation, evaluation-methodology,
and evaluation-execution decisions together with their named approvers,
approval capacities, dates, sources, authorization boundaries, and amendment
history.

Canonical status is limited to evaluation-workstream decisions recorded here.
This log does not replace or grant authority over:

- Leng's proposed-method design and approval process;
- shared runtime or cross-workstream contract approval;
- research-methodology approval outside the recorded decision scope;
- data-governance, ethics, consent, licensing, or dataset-access approval;
- configuration or comparator freeze; or
- validation or held-out execution authorization.

The first entry records the six Task 2.5C2A receipt-join decisions expressly
approved in the supplied FYP project conversation. It does not retroactively
approve any other pending item in
`docs/proposed_evaluation_receipt_join_alignment_contract_v0.md`.

## 2. Authority and approval-evidence conventions

Every approval entry must state:

- the decision ID and status;
- the exact decision text or a stable repository reference containing it;
- decision date;
- approver's supplied name;
- role or roles in which that person approved;
- approval-source type and source description;
- repository foundation and related review reference, when applicable;
- authorized implementation boundary;
- implementation-acceptance state;
- evaluation-freeze state; and
- predecessor, amendment, or supersession links when applicable.

An approver name and role record who was stated to approve a decision. They do
not constitute a signature, identity authentication, or proof of independence.
A Git commit, merge, pull request, hash, source string, or populated provenance
field is not approval evidence unless the applicable approval process expressly
records it as such.

Approval evidence must be described at its actual strength. For the initial
entry, the evidence is an explicit user-provided FYP project conversation
approval and named-role confirmation. No immutable conversation-message ID,
cryptographic signature, authenticated identity assertion, GitHub approval, or
signed-off commit was supplied. The repository foundation and PR identify the
design context only; they do not independently prove the approval.

Independent review of this log is a later gate. This entry does not claim that
such review has occurred.

## 3. Decision record identifiers

Decision IDs are stable log keys and must not be reused for a different
decision.

- Existing decision IDs from an approved proposal are retained exactly, such
  as `SCH-JA-01` through `SCH-JA-04`.
- A decision that did not previously have an approved identifier receives a
  new evaluation-log-local ID in the `EVAL-...` namespace.
- Approval-entry IDs identify log envelopes and are not conversation-message
  identifiers, signatures, or external authentication evidence.
- Amendment and supersession records receive new IDs; they do not overwrite the
  ID or text of the earlier record.

The following IDs introduced in the initial entry are local administrative
identifiers assigned by this log, not previously approved `SCH-JA` IDs:

- `EVAL-JA-05` — cardinality and selected-population decision; and
- `EVAL-JA-06` — immutable join-set revision handling.

The initial approval-envelope ID is
`EVAL-APP-2026-10-27-C2A-01`. It identifies this log entry only.

## 4. Decision and lifecycle status definitions

### Decision status

- `PROPOSED`: recorded for consideration but not approved.
- `APPROVED`: approved by the named approver in the recorded role and only for
  the stated boundary.
- `AMENDED`: a later separately identified record changes part of the decision;
  both records remain in history.
- `SUPERSEDED`: a later separately identified decision replaces the earlier
  decision for future work; the earlier record remains historical evidence.
- `REJECTED`: expressly rejected by the named decision authority.

### Design, implementation, and freeze status

These statuses are independent:

- `DESIGN_APPROVED_FOR_SYNTHETIC_IMPLEMENTATION` means a later, separately
  authorized task may implement the recorded design using synthetic data only
  and within the stated boundary.
- `IMPLEMENTATION_NOT_YET_ACCEPTED` means no implementation is accepted merely
  because the design is approved. Implementation requires its own task,
  verification, and independent review/acceptance.
- `NOT EVALUATION_FROZEN` means the decision does not freeze methodology,
  software, data, configuration, evidence, or execution state and does not
  authorize validation or held-out evaluation.

This documentation task creates the log and registers supplied approvals only.
It does not itself authorize or perform implementation.

## 5. Named approver and role registry

The supplied role confirmation for the initial entry is:

| Person | Confirmed role |
| --- | --- |
| Tai Yong Xin | Evaluation Lead |
| Tai Yong Xin | Schema Owner |
| Tai Yong Xin | Validator Owner |
| Tai Yong Xin | Data Manifest Owner |

Tai Yong Xin occupies all four roles. These are four approval capacities held
by one named individual, not four independent people and not evidence of four
independent reviews. No separate independent approver or real-data identity
verifier is recorded.

Future entries must name the person and the exact role used for that decision.
They must not infer role authority from authorship, repository access, a commit,
or a prior approval with a different scope.

## 6. Date and source-reference conventions

Dates use ISO `YYYY-MM-DD` in structured entry fields, with a human-readable
form where useful. A date records the supplied decision date; it is not a
trusted timestamp unless independently authenticated evidence is explicitly
recorded.

Source references must distinguish:

- a descriptive conversation approval source;
- a repository design foundation or proposal;
- an external approval record, if one is later supplied; and
- independent review or authentication evidence, if separately established.

For the initial entry:

- decision date: `2026-10-27` (27 October 2026);
- approval source: explicit user-provided FYP project conversation approvals
  and named-role confirmation;
- repository foundation: merge commit `4a91578`, PR `#29`; and
- proposal context:
  `docs/proposed_evaluation_receipt_join_alignment_contract_v0.md`.

No immutable conversation-message identifier is available and none is
invented. PR `#29` and commit `4a91578` identify the merged proposal foundation;
they are not represented as GitHub approval or signed approval evidence.

## 7. Implementation authorization boundaries

The six initial decisions approve the design for a later synthetic-only
receipt-join implementation. Subject to a separate implementation task, the
approved boundary includes only:

- receipt-join schema records;
- a structural validator;
- alignment-readiness validator interfaces and checks operating within the
  approved trust boundary;
- deterministic serialization;
- synthetic tests;
- development documentation; and
- evaluation-package exports for those approved interfaces.

The approval expressly excludes:

- real receipt datasets, annotations, joins, or identity evidence;
- automatic receipt-to-reference inference;
- a prediction-to-reference row-alignment algorithm;
- normalization or edit-distance matching;
- threshold-grid development or threshold fitting;
- evaluation metrics or denominator computation;
- actual verification or authentication of real mappings;
- dataset, ethics, consent, licensing, or access authorization;
- validation or held-out execution;
- configuration, methodology, comparator, or evaluation freeze;
- runtime contract changes; and
- Leng-owned proposed-method contract or pipeline changes.

No implementation is created or accepted by this log. After independent review
of the log, a separately authorized synthetic implementation task remains
required, followed by implementation verification and acceptance.

## 8. Append-only history, amendment, and supersession

Decision history is append-only at the logical record level:

1. An existing decision record, approver attribution, date, source description,
   or authorization boundary must not be silently rewritten.
2. A correction or change requires a new amendment or supersession record with
   its own ID, date, named approver/role, source evidence, reason, and exact
   predecessor ID.
3. The new record must state which earlier clauses remain active, which change,
   and the effective boundary for future work.
4. Superseded records remain visible as historical evidence.
5. Two incompatible active successors for one predecessor are a decision-log
   conflict and must fail closed pending explicit resolution.
6. Missing, unauthenticated, or contradictory approval evidence must not be
   upgraded or repaired by inference.

Git history supports repository traceability but is not, by itself, an
immutable approval registry or cryptographic audit log. Any future signed or
external approval registry must be referenced explicitly without rewriting the
historical evidence level recorded here.

## 9. Task 2.5C2A receipt-join approval entry

### 9.1 Approval envelope

| Field | Recorded value |
| --- | --- |
| Approval-entry ID | `EVAL-APP-2026-10-27-C2A-01` — local log ID, not a conversation-message ID |
| Decision date | `2026-10-27` |
| Approval source | Explicit user-provided FYP project conversation approvals and named-role confirmation |
| Source-evidence strength | Supplied conversation approval; not independently authenticated |
| Design foundation | Merge commit `4a91578`, PR `#29` |
| Proposal context | `docs/proposed_evaluation_receipt_join_alignment_contract_v0.md` |
| Authorization | Synthetic-only receipt-join schema and validator boundary described in Section 7 |
| Design status | `DESIGN_APPROVED_FOR_SYNTHETIC_IMPLEMENTATION` |
| Implementation status | `IMPLEMENTATION_NOT_YET_ACCEPTED` |
| Current task implementation authorization | `NOT AUTHORIZED IN THIS TASK` |
| Freeze status | `NOT EVALUATION_FROZEN` |
| Independent review | Required as a separate subsequent gate; not yet recorded |
| Amendment/supersession | None recorded at creation |

### 9.2 `SCH-JA-01` — terminal receipt coverage

| Field | Recorded value |
| --- | --- |
| Decision ID | `SCH-JA-01` |
| Status | `APPROVED` |
| Decision | Require exactly one terminal receipt-coverage outcome per applicable receipt side: `JOINED`, `REFERENCE_ONLY`, or `PREDICTION_ONLY`. Require complete, nonduplicated coverage of the scoped prediction and selected reference populations. |
| Approver | Tai Yong Xin |
| Approval role | Evaluation Lead |
| Date/source | `2026-10-27`; approval envelope `EVAL-APP-2026-10-27-C2A-01` |
| Authorization boundary | Section 7 synthetic-only boundary |
| Implementation/freeze | `IMPLEMENTATION_NOT_YET_ACCEPTED`; `NOT EVALUATION_FROZEN` |

### 9.3 `SCH-JA-02` — immutable prediction scope

| Field | Recorded value |
| --- | --- |
| Decision ID | `SCH-JA-02` |
| Status | `APPROVED` |
| Decision | Each join set references one complete immutable prediction-bundle scope. Mixed systems, runs, configurations, or bundle revisions are prohibited. |
| Approver | Tai Yong Xin |
| Approval roles | Evaluation Lead; Schema Owner |
| Date/source | `2026-10-27`; approval envelope `EVAL-APP-2026-10-27-C2A-01` |
| Authorization boundary | Section 7 synthetic-only boundary |
| Implementation/freeze | `IMPLEMENTATION_NOT_YET_ACCEPTED`; `NOT EVALUATION_FROZEN` |

### 9.4 `SCH-JA-03` — outcome-specific evidence

| Field | Recorded value |
| --- | --- |
| Decision ID | `SCH-JA-03` |
| Status | `APPROVED` |
| Decision | Require outcome-specific evidence. For `JOINED`, evidence concerns the declared identity association. For `REFERENCE_ONLY` and `PREDICTION_ONLY`, evidence concerns coverage and absence, not a fabricated pair association. Structural metadata must remain distinct from independently authenticated verification evidence. |
| Approver | Tai Yong Xin |
| Approval role | Evaluation Lead |
| Date/source | `2026-10-27`; approval envelope `EVAL-APP-2026-10-27-C2A-01` |
| Authorization boundary | Section 7 synthetic-only boundary |
| Implementation/freeze | `IMPLEMENTATION_NOT_YET_ACCEPTED`; `NOT EVALUATION_FROZEN` |

### 9.5 `SCH-JA-04` — structural validity versus readiness

| Field | Recorded value |
| --- | --- |
| Decision ID | `SCH-JA-04` |
| Status | `APPROVED` |
| Decision | Structural validity and alignment readiness must be separately validated. Structural validity alone does not authorize evaluation. |
| Approver | Tai Yong Xin |
| Approval roles | Evaluation Lead; Validator Owner |
| Date/source | `2026-10-27`; approval envelope `EVAL-APP-2026-10-27-C2A-01` |
| Authorization boundary | Section 7 synthetic-only boundary |
| Implementation/freeze | `IMPLEMENTATION_NOT_YET_ACCEPTED`; `NOT EVALUATION_FROZEN` |

### 9.6 `EVAL-JA-05` — cardinality and selected population

`EVAL-JA-05` is a new local log identifier. It is not a previously approved
`SCH-JA` identifier; the decision text itself is recorded as approved by the
supplied conversation authorization.

| Field | Recorded value |
| --- | --- |
| Decision ID | `EVAL-JA-05` — newly introduced evaluation-log-local ID |
| Status | `APPROVED` |
| Decision | Require one-to-one associations within a join set, complete prediction coverage, and complete reference coverage for the manifest partition/cohort intersection. Preserve manifest identity and revision for reproducibility. |
| Approver | Tai Yong Xin |
| Approval roles | Evaluation Lead; Data Manifest Owner |
| Date/source | `2026-10-27`; approval envelope `EVAL-APP-2026-10-27-C2A-01` |
| Authorization boundary | Section 7 synthetic-only boundary |
| Implementation/freeze | `IMPLEMENTATION_NOT_YET_ACCEPTED`; `NOT EVALUATION_FROZEN` |

### 9.7 `EVAL-JA-06` — immutable revision handling

`EVAL-JA-06` is a new local log identifier. It is not a previously approved
`SCH-JA` identifier; the decision text itself is recorded as approved by the
supplied conversation authorization.

| Field | Recorded value |
| --- | --- |
| Decision ID | `EVAL-JA-06` — newly introduced evaluation-log-local ID |
| Status | `APPROVED` |
| Decision | Join-set revisions must be immutable and append-only, with predecessor identity, amendment reason, provenance, and deterministic conflict detection. |
| Approver | Tai Yong Xin |
| Approval roles | Schema Owner; Evaluation Lead |
| Date/source | `2026-10-27`; approval envelope `EVAL-APP-2026-10-27-C2A-01` |
| Authorization boundary | Section 7 synthetic-only boundary |
| Implementation/freeze | `IMPLEMENTATION_NOT_YET_ACCEPTED`; `NOT EVALUATION_FROZEN` |

## 10. Approval-integrity limitations and remaining gate

This entry records supplied design approval. It does not establish:

- four independent approvers or reviews;
- an independent schema, validator, manifest, or real-data identity verifier;
- a handwritten, electronic, or cryptographic signature;
- cryptographic authentication of the conversation or approver identity;
- an immutable conversation-message identifier;
- a GitHub review, approval, or signed-off commit;
- correctness or acceptance of a future implementation;
- actual dataset eligibility, mapping verification, or access authority; or
- evaluation, configuration, software, methodology, or held-out freeze.

The remaining immediate gate is independent review of this decision-log entry.
Only after that review may a separately authorized task implement the approved
synthetic-only receipt-join schema and validators. That implementation will
remain unaccepted until its own independent review and explicit acceptance.

No other receipt-join, row-alignment, normalization, threshold, metric,
dataset, runtime, or proposed-method decision is approved by this entry.

## 11. Task 2.5C2B row-alignment schema approval entry

### 11.1 Approval envelope and authorization boundary

| Field | Recorded value |
| --- | --- |
| Approval-entry ID | `EVAL-APP-2026-10-27-C2B-01` — local log ID, not a conversation-message ID |
| Decision date | `2026-10-27` (27 October 2026) |
| Approval source | Explicit user-provided FYP project conversation approval, dated 27 October 2026 |
| Source-evidence strength | Supplied conversation approval; not independently authenticated |
| Repository foundation | Commit `2206692`; identifies implementation context only and is not approval evidence |
| Proposal context | `docs/proposed_evaluation_receipt_join_alignment_contract_v0.md` |
| Named approver | Tai Yong Xin |
| Registered role authority used | Evaluation Lead; Schema Owner |
| Role-attribution limitation | Existing registered roles held by one named person; not a new appointment, separate role-specific attestation, or independent approval |
| Design status | `DESIGN_APPROVED_FOR_SYNTHETIC_IMPLEMENTATION` |
| Implementation status | `IMPLEMENTATION_NOT_YET_ACCEPTED` |
| Current task implementation authorization | `NOT AUTHORIZED IN THIS TASK` |
| Freeze status | `NOT EVALUATION_FROZEN` |
| Independent review | Required as a separate subsequent gate; not recorded by this entry |
| Amendment/supersession | None; the earlier six approvals remain active and unchanged |

Subject to a later, separately authorized implementation task, this approval
permits synthetic-only development of:

- row-alignment link records;
- completed, blocked, and unexecuted alignment states;
- structural validators;
- complete-coverage and one-to-one-cardinality checks for completed
  alignments;
- deterministic serialization;
- synthetic tests;
- development documentation; and
- evaluation-package exports for the approved interfaces.

This approval expressly excludes:

- an actual row-matching algorithm;
- text normalization;
- Levenshtein distance or other similarity scoring;
- matching thresholds;
- tie-breaking and source-order methodology;
- metric or denominator computation;
- real dataset operations;
- validation or held-out evaluation;
- runtime extraction changes; and
- Leng-owned proposed-method changes.

These decisions do not constitute real identity verification, methodology
freeze, dataset authorization, or evaluation authorization. No implementation
is created or accepted by this log entry.

### 11.2 `SCH-JA-05` — row-alignment states and complete coverage

| Field | Recorded value |
| --- | --- |
| Decision ID | `SCH-JA-05` |
| Status | `APPROVED` |
| Approver | Tai Yong Xin |
| Approval roles | Evaluation Lead; Schema Owner — existing registered roles, not separate attestations |
| Date/source | `2026-10-27`; explicit user-provided FYP project conversation approval; envelope `EVAL-APP-2026-10-27-C2B-01` |
| Authorization boundary | Section 11.1 synthetic-only boundary |
| Implementation/freeze | `IMPLEMENTATION_NOT_YET_ACCEPTED`; `NOT EVALUATION_FROZEN` |

Approved decision:

Explicit row-alignment links shall use `MATCHED`, `REFERENCE_ONLY`, and
`PREDICTION_ONLY` states.

Prediction-row and reference-row identities remain independent.

A completed row alignment must account for every in-scope prediction row and
reference row exactly once, with no duplicate or conflicting matches and
one-to-one cardinality.

Blocked or unexecuted alignment must be represented separately, with an
explicit reason and provenance, without fabricated row links.

A fallback receipt containing no prediction rows must not be interpreted as
proof that the alignment algorithm executed.

The schema must distinguish completion, blocking, and nonexecution without
automatically assigning evaluation metrics or denominator consequences.

### 11.3 `SCH-JA-06` — immutable links and representational serialization

| Field | Recorded value |
| --- | --- |
| Decision ID | `SCH-JA-06` |
| Status | `APPROVED` |
| Approver | Tai Yong Xin |
| Approval roles | Evaluation Lead; Schema Owner — existing registered roles, not separate attestations |
| Date/source | `2026-10-27`; explicit user-provided FYP project conversation approval; envelope `EVAL-APP-2026-10-27-C2B-01` |
| Authorization boundary | Section 11.1 synthetic-only boundary |
| Implementation/freeze | `IMPLEMENTATION_NOT_YET_ACCEPTED`; `NOT EVALUATION_FROZEN` |

Approved decision:

Row-alignment link records must be versioned and immutable.

Serialization must be deterministic and identity-based, independent of input
tuple order.

Canonical serialization order is representational only. It must not be
interpreted as:

- receipt source order;
- reference-row source order;
- prediction-row source order; or
- matcher execution order.

Exact serialization mechanics remain provisional development choices unless
separately approved.

### 11.4 Approval-integrity limitations and outstanding conditions

This entry records one named person's supplied design approval under existing
registered evaluation-workstream roles. It does not establish:

- a signature or authenticated identity assertion;
- a separate role-specific attestation;
- an independent reviewer or second approver;
- an immutable conversation-message identifier;
- an external approval record;
- correctness or acceptance of a future implementation;
- approval of row-matching, normalization, distance, threshold, tie-breaking,
  source-order, metric, or denominator methodology;
- real-data, dataset, validation, or held-out authorization; or
- evaluation, methodology, configuration, software, or evidence freeze.

The immediate outstanding condition is independent review of this appended
approval entry. A separate implementation task and later implementation review
and acceptance remain required before these decisions have accepted executable
form.

## 12. Task 2.5C2C deterministic row-matcher owner-approval entry

### 12.1 Approval envelope

| Field | Proposed recorded value |
|---|---|
| Approval-entry ID | `EVAL-APP-2026-10-31-C2C-01` — proposed evaluation-log-local ID, not a conversation-message identifier |
| Decision date | `2026-10-31` |
| Named approver | Tai Yong Xin |
| Recorded approval capacity | Task Owner, Extraction and Evaluation Workstream; existing registered Evaluation Lead |
| Approval source | Direct supplied project-conversation statement, `approve all`, approving by reference the immediately preceding 30 October 2026 methodology review and its exact amendments |
| Evidence strength | Supplied conversational owner approval; no immutable conversation-message ID, signature, authenticated identity assertion, independent timestamp, GitHub approval or external approval record |
| Methodology-review source | Supplied 30 October 2026 project-conversation technical review; assistant-authored specification supporting the owner decision, not an independent human approval |
| Repository foundation | PR #33 merge `3d64793`; current evaluation foundation `6351e2f`; repository revisions identify context only and are not approval evidence |
| Proposal context | `docs/proposed_evaluation_receipt_join_alignment_contract_v0.md` |
| Owner-level decision status | `APPROVED` within Tai’s recorded owner capacity |
| Separate methodology approval | Required; not supplied |
| Separate annotation/reference approval | Required for `MTH-JA-06`; not supplied |
| Separate configuration/conformance approval | Required; not supplied |
| Effective for synthetic matcher implementation | `NO` |
| Implementation status | `NOT AUTHORIZED`; `NOT IMPLEMENTED`; `NOT ACCEPTED` |
| Freeze status | `NOT EVALUATION_FROZEN` |
| Independent review | Required; not recorded |
| Amendment/supersession | New resolution of pending C2C questions; does not amend or supersede `SCH-JA-01` through `SCH-JA-06`, `EVAL-JA-05`, or `EVAL-JA-06` |

This envelope records Tai Yong Xin’s supplied owner-level approval. It does not represent Tai as an independent methodology reviewer, annotation reviewer, governance approver or independent implementation reviewer. Required separate human confirmations remain unsatisfied.

### 12.2 `TAI-JA-01` — Prediction row order

| Field | Proposed value |
|---|---|
| Status | `APPROVED` at Tai-owner level |
| Separate approval required | Named methodology reviewer |
| Effective for synthetic implementation | `NO` |
| Date/source | `2026-10-31`; envelope `EVAL-APP-2026-10-31-C2C-01` |

Approved owner rule:

1. The monotonic matcher shall use a separately declared, versioned and verified prediction-order evidence record.
2. The evidence shall bind to the complete prediction scope, exact bundle, receipt, producer artifact and producer version.
3. It shall identify every applicable prediction row exactly once and assign a dense permutation of positions `0..n-1`.
4. Original immutable prediction-row IDs shall be preserved.
5. Declaration provenance and independent verification provenance shall be distinct.
6. The declaration shall exist before access to reference descriptions, match labels or matcher results.
7. Missing rows, extra rows, duplicate row IDs, duplicate positions, non-dense positions, conflicting evidence, scope mismatch or unverifiable producer binding shall invalidate the evidence.
8. `PredictionItemRow.output_ordinal`, dictionary iteration, copied reference order and copied `source_order` shall not independently establish semantic prediction order.
9. A `JOINED` receipt without valid order evidence shall not produce a completed monotonic alignment.
10. Synthetic fixtures may declare synthetic order evidence if it is explicitly labelled synthetic and makes no authenticated evaluation-provenance claim.

Remaining conditions:

- Identify the real B1/B2/B3 producer artifact and evidence route.
- Define and approve the order-evidence record schema and verifier.
- Obtain separate methodology approval.

### 12.3 `MTH-JA-01` — Description normalization

| Field | Proposed value |
|---|---|
| Status | `APPROVED` at Tai-owner level |
| Separate approval required | Named methodology reviewer |
| Effective for synthetic implementation | `NO` |
| Date/source | `2026-10-31`; envelope `EVAL-APP-2026-10-31-C2C-01` |

Approved owner rule:

1. Accept only Unicode strings.
2. Reject input containing unpaired surrogate code points.
3. Apply Unicode NFKC using the frozen Unicode profile.
4. Apply locale-independent full Unicode case folding.
5. Collapse each maximal run of the Unicode 16.0 `White_Space` set to one U+0020 ASCII space. The set is:

   `U+0009–U+000D`, `U+0020`, `U+0085`, `U+00A0`, `U+1680`,
   `U+2000–U+200A`, `U+2028`, `U+2029`, `U+202F`, `U+205F`, `U+3000`.

6. Remove leading and trailing U+0020 after whitespace collapse.
7. Preserve every remaining code point, including punctuation. No quote, dash, retailer, product or other contextual rewriting is permitted.
8. An available description that normalizes to the empty string is unusable and follows `MTH-JA-06`.
9. The initial profile is tied to CPython `3.14.4` with `unicodedata`/UCD `16.0.0`, or to a language-neutral Unicode 16.0 implementation proven equivalent by the same approved conformance corpus.

Remaining conditions:

- Assign the normalization profile ID and version.
- Approve the cross-runtime conformance corpus and digest.
- Decide whether normalized outputs are stored or reproducibly recomputed.
- Obtain separate methodology approval.

### 12.4 `MTH-JA-02` — Normalized Levenshtein distance

| Field | Proposed value |
|---|---|
| Status | `APPROVED` at Tai-owner level |
| Separate approval required | Named methodology reviewer |
| Effective for synthetic implementation | `NO` |
| Date/source | `2026-10-31`; envelope `EVAL-APP-2026-10-31-C2C-01` |

Approved owner rule:

For normalized descriptions `a` and `b`, Levenshtein operates on Unicode code points.

For nonempty strings, retain:

- `edit_count = Lev(a,b)`;
- `max_length = max(len(a),len(b))`; and
- exact distance `edit_count/max_length`.

The threshold shall be represented as a canonical reduced rational `p/q`, with `q > 0` and `0 ≤ p ≤ q`. Eligibility shall be determined without binary floating point:

\[
\text{edit\_count}\times q \le p\times\text{max\_length}.
\]

Additional rules:

- Equal nonempty normalized strings are classified as `EXACT_NORMALIZED_DESCRIPTION`, not approximate matches.
- If exactly one normalized string is empty, the distance is exactly `1/1`.
- If both normalized strings are empty, comparison is unusable and follows `MTH-JA-06`; it is not an exact match.
- Binary floating point shall not control eligibility, objective comparison or stored distance evidence.

Remaining conditions:

- Explicitly specify unit edit costs and executable base cases.
- Define canonical rational serialization.
- Approve cross-runtime arithmetic fixtures.
- Obtain separate methodology approval.

### 12.5 `MTH-JA-03` — Global monotonic matching

| Field | Proposed value |
|---|---|
| Status | `APPROVED` at Tai-owner level |
| Separate approval required | Named methodology reviewer |
| Effective for synthetic implementation | `NO` |
| Date/source | `2026-10-31`; envelope `EVAL-APP-2026-10-31-C2C-01` |

Approved owner rule:

1. Sort prediction and reference rows by their approved dense order positions.
2. All selected matches, including exact matches, shall form one strictly increasing, non-crossing path.
3. Each prediction and reference row may participate in at most one match.
4. A nonexact edge is permitted only when its exact normalized Levenshtein distance is within the supplied threshold.
5. Select the path using this lexicographic objective:

   1. maximize the number of nonempty exact normalized pairs;
   2. maximize the total number of permitted pairs;
   3. minimize the exact rational sum of normalized Levenshtein distances;
   4. minimize the sum of absolute differences between dense zero-based prediction and reference positions;
   5. apply `MTH-JA-05`.

6. Objective 1 has priority over objective 2. A path with more exact pairs wins even when this reduces the total number of matches.
7. Raw, non-dense source-rank values shall not be subtracted for displacement.
8. Every unselected prediction or reference row shall be retained explicitly as unmatched.
9. No reference correctness value or downstream metric effect may influence path selection.

Remaining conditions:

- Approve an executable recurrence or equivalent conformance definition.
- Define exact rational-sum serialization/comparison.
- Obtain separate methodology approval.

### 12.6 `MTH-JA-04` — Duplicate-description assignment

| Field | Proposed value |
|---|---|
| Status | `APPROVED` at Tai-owner level |
| Separate approval required | Named methodology reviewer |
| Effective for synthetic implementation | `NO` |
| Date/source | `2026-10-31`; envelope `EVAL-APP-2026-10-31-C2C-01` |

Approved owner rule:

1. Preserve every prediction and reference row identity, including rows with identical normalized descriptions.
2. Do not collapse, merge, deduplicate or locally pre-pair duplicate descriptions.
3. Treat every permitted occurrence pair as a distinct candidate edge.
4. Assign duplicate occurrences only through the global objective in `MTH-JA-03` and total ordering in `MTH-JA-05`.
5. Preserve surplus prediction and reference occurrences as explicit unmatched rows.
6. Do not use correctness labels, unrelated reference fields, dictionary order or downstream metric effects to resolve duplicate assignment.

Remaining conditions:

- Approve adversarial duplicate fixtures.
- Obtain separate methodology approval.

### 12.7 `MTH-JA-05` — Complete deterministic tie-breaking

| Field | Proposed value |
|---|---|
| Status | `APPROVED` at Tai-owner level |
| Separate approval required | Named methodology reviewer |
| Effective for synthetic implementation | `NO` |
| Date/source | `2026-10-31`; envelope `EVAL-APP-2026-10-31-C2C-01` |

Approved owner rule:

After the first four objectives in `MTH-JA-03` are equal, compare in order:

1. the matched reference dense-position sequence lexicographically;
2. the matched prediction dense-position sequence lexicographically;
3. the sequence of `(prediction_row_id, reference_row_id)` pairs lexicographically.

ID and path comparison shall use these rules:

- Use original immutable IDs without normalization or case folding.
- Compare strings by their Unicode code-point integer sequences.
- If one sequence is an exact prefix of another, the shorter sequence sorts first.
- Apply the same lexicographic prefix rule to variable-length paths.
- Although tied paths normally have equal match counts, variable-length behavior remains defined.
- Equality of the final ID-pair sequence means the selected match path is identical; no unresolved alternative remains.
- Dictionary insertion order, hash iteration order and reference correctness labels shall have no effect.

Remaining conditions:

- Approve shuffled-input and cross-runtime total-order fixtures.
- Obtain separate methodology approval.

### 12.8 `MTH-JA-06` — Missing and unavailable descriptions

| Field | Proposed value |
|---|---|
| Status | `APPROVED` at Tai-owner level |
| Separate approval required | Named methodology reviewer and named annotation/reference owner |
| Effective for synthetic implementation | `NO` |
| Date/source | `2026-10-31`; envelope `EVAL-APP-2026-10-31-C2C-01` |

Approved owner rule:

| State | Handling |
|---|---|
| Prediction description `MISSING` | Forced unmatched; preserve row and state |
| Prediction description `UNRESOLVED` | Forced unmatched; preserve row, state and reason |
| Finalized reference description `UNAVAILABLE` | Block receipt alignment unless a separately approved, truth-independent alternate row-association route exists |
| Reference adjudication pending | Block receipt alignment |
| Draft or unfinalized reference | Block receipt alignment |
| Available description normalizes to empty | Block as malformed or unusable |
| Invalid type or unpaired surrogate | Block receipt alignment |
| Invalid identity, order evidence, threshold or configuration | Block receipt alignment |

For completed alignments, forced-unmatched prediction rows remain in the complete coverage ledger.

For blocked alignments, preserve the immutable source binding and source inventories, but do not fabricate row links, execution evidence, partial completion or metric consequences.

Adjudication-pending truth shall not be treated as finalized unavailable truth.

Remaining conditions:

- Approve downstream population and metric consequences separately.
- Approve any alternate association route separately.
- Obtain separate methodology and annotation/reference-owner approvals.

### 12.9 `EVAL-MCFG-01` — Matcher-configuration contract

`EVAL-MCFG-01` is a proposed evaluation-log-local administrative ID. It is not a previously approved decision ID.

| Field | Proposed value |
|---|---|
| Status | `APPROVED` at Tai-owner level |
| Separate approval required | Named methodology/configuration reviewer and named conformance reviewer |
| Effective for synthetic implementation | `NO` |
| Date/source | `2026-10-31`; envelope `EVAL-APP-2026-10-31-C2C-01` |

Approved owner rule:

Each matcher configuration shall be immutable and versioned and contain:

- configuration ID and version;
- predecessor identity and amendment reason when applicable;
- normalization profile ID/version;
- distance formula ID/version;
- monotonic-objective ID/version;
- tie-breaking ID/version;
- missing/unavailable-description policy ID/version;
- prediction-order policy version;
- exact order-evidence record reference;
- threshold numerator and denominator as a reduced rational;
- threshold provenance classification;
- runtime, Unicode and arithmetic compatibility profile;
- matcher implementation/software version;
- canonical serialization version;
- declared digest algorithm and content digest;
- conformance-fixture identity and verified digest; and
- provenance for configuration creation and review.

A threshold used only for synthetic matcher tests shall be classified explicitly as `SYNTHETIC_FIXED_NOT_FITTED`. It shall not carry trained, selected, validation-frozen or evaluation-frozen status.

Configuration history shall be append-only. Changes require a new version, predecessor identity, amendment reason, provenance and review evidence. Conflicting active successors shall fail closed.

Remaining conditions:

- Define the exact record schema and field types.
- Define canonical serialization bytes.
- Select the digest algorithm and digest scope.
- Define threshold-provenance enums and validation rules.
- Create and approve the conformance corpus and verified digest.
- Approve configuration amendment/conflict validation.
- Obtain separate methodology/configuration and conformance approvals.

### 12.10 Envelope restrictions

This envelope does not authorize:

- matcher implementation;
- synthetic implementation files or tests;
- real prediction-order evidence production;
- threshold-grid creation or threshold fitting;
- treating a synthetic threshold as trained;
- real receipt matching;
- metric or denominator computation;
- dataset access;
- validation or held-out execution;
- comparator, configuration, methodology, software or evidence freeze;
- modification of runtime or proposed-method contracts; or
- modification of previously approved `SCH-JA` decisions.

`TAI-JA-02`, `MTH-JA-07`, `MTH-JA-08`, applicable governance decisions and proposed-method integration decisions remain pending.
