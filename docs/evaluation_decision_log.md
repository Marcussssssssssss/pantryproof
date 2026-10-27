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
