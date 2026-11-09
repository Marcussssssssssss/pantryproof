# S-06 Failure-Stage Matrix Clarification

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_FULL_CONTRACT_APPROVAL_PENDING`

**Repository:** `D:/PantryProof`  
**Branch:** `feature/tai-android-ui`  
**HEAD reviewed:** `f218e0ed5f741c0b113a46d0f23f99c27dc45cb7`  
**Parent package:** `M3D-0R-PROPOSAL-2026-11-04`  
**Date:** 2026-11-04

## 1. Scope and preservation

This document clarifies only the agreed presentation-layer S-06 failure
matrix. It does not approve or implement orchestration, Kotlin/Python code, OCR,
extraction, scoring, persistence, or evaluation.

Leng's L-S06-01 through L-S06-08 backend response is recorded here as six
`APPROVED` subdecisions and two `APPROVED_WITH_EXCEPTION` subdecisions. This is
the backend decision history preceding the shared agreement below. Leng's
complete L-01 through L-07 review, Tai's T-01 through T-07 review, and all
non-S-06 shared decisions remain pending.

Leng's separately dated `APPROVE WITH EXCEPTIONS — S-06 SHARED RESOLUTION`
response of 2026-11-04 resolves the three outcome-profile questions recorded as
L-S06-R2-01 through L-S06-R2-03 below. Tai approved those reconciled rules, and
Leng subsequently acknowledged and accepted Tai's confirmation. S-06 is now
`S06_SHARED_OWNER_DESIGN_AGREED`. This does not approve Tai's T-01 through T-07,
Leng's L-01 through L-07, any other shared decision, or implementation.

The original M3D-0 draft and fixture bytes are not modified. M3D-0R decision
documents are updated only to record the agreement and remaining approval state.
The stage names `AVAILABILITY`, `OCR`, `SOURCE_GATE`, `EXTRACTION`, and
`PRESENTATION_ADAPTER` remain presentation-layer taxonomy rather than Contract
V0 enums.

## 2. Contract V0 evidence boundary

The clarification must not be presented as existing Contract V0 behavior:

- `SourceProcessingStatus` defines `RECEIVED`, `OCR_COMPLETED`, `OCR_PARTIAL`,
  and `OCR_FAILED`, but Contract V0 defines no legal transition order or
  relationship among processing status, token count, and gate decision.
- `AdaptedOcrSource` is gate-free and accepts any caller-supplied
  `SourceProcessingStatus` that satisfies its structural checks.
- A full Contract V0 `ReceiptSourceEvidence` always contains a recorded gate.
  The presentation `sourceEvidence` object used with `sourceGate: null` is
  therefore only a pre-gate evidence summary, not a serialized
  `ReceiptSourceEvidence`.
- `attach_gate_result()` structurally permits either gate decision with any
  processing status when receipt identity matches.
- B1/B2 consume already-gated evidence. They map `INSUFFICIENT` to
  `FALLBACK_NO_UPDATE`; a sufficient gate enters extraction.
- `ReceiptOutput` forbids insufficient evidence, but Contract V0 does not forbid
  a sufficient gate paired with `RECEIVED` or `OCR_FAILED` processing status.
- Contract V0 `FailureStage` contains only `PRE_RESOLUTION` and
  `INVENTORY_PERSISTENCE`. It does not define the five S-06 stages.

Consequently, every status/stage restriction below is an agreed fail-closed
S-06 **presentation profile**. Leng's recorded backend response supplies the
backend conditions for technical-failure envelopes. The two original exceptions
and the later R2 resolution are recorded below. Their S-06 shared-owner agreement
is complete; the rest of the M3D contract remains pending.

## 3. Existing four terminal outcomes

The clarified matrix retains, and does not add to, the four outcomes proposed
by M3D-0R:

1. `RESULT_AVAILABLE`
2. `PROCESSING_UNAVAILABLE`
3. `PROCESSING_FAILED`
4. `SOURCE_EVIDENCE_INSUFFICIENT`

Their separation remains:

- capability absence uses `PROCESSING_UNAVAILABLE`;
- a technical exception uses `PROCESSING_FAILED`;
- a recorded `INSUFFICIENT` gate uses `SOURCE_EVIDENCE_INSUFFICIENT` only when
  that presentation response is successfully constructed;
- a returned Contract V0 `ReceiptOutput`, including one with preserved
  `extractionStatus: FAILED`, uses `RESULT_AVAILABLE`.

Therefore `AVAILABILITY` is not a valid stage under `PROCESSING_FAILED`, and an
insufficient gate is not a technical failure.

If an actual `INSUFFICIENT` gate is recorded but a subsequent backend
presentation/projection operation fails, no successful insufficient-evidence
response exists. That lifecycle is
`DEFERRED — OUTSIDE V1 JSON CONFORMANCE`; it is not silently mapped to
`SOURCE_GATE`, `PRESENTATION_ADAPTER`, `PROCESSING_UNAVAILABLE`, or an invented
fifth outcome.

## 4. Agreed outcome and stage matrices

Legend:

- **Required**: member must be present and non-null.
- **Optional**: member may be null or present as constrained.
- **Null**: member must be explicitly null.
- **Shared condition agreed**: the condition is included in the recorded S-06
  shared-owner design agreement; full M3D contract approval remains pending.

**Terminal-outcome matrix**

| Outcome | `sourceEvidence` | `sourceGate` | `failure` | `automaticExtraction` / `receipt` |
|---|---|---|---|---|
| `RESULT_AVAILABLE` | Required genuine evidence; preserve any one of `RECEIVED`, `OCR_COMPLETED`, `OCR_PARTIAL`, or `OCR_FAILED` | Required actual source-bound `SUFFICIENT` gate | Null | Both required from a structurally valid Contract V0 `ReceiptOutput` |
| `PROCESSING_UNAVAILABLE` | Null | Null | Required `AVAILABILITY` failure | Both null |
| `PROCESSING_FAILED` | Constrained by technical-failure stage below | Constrained by technical-failure stage below | Required technical failure | Both null |
| `SOURCE_EVIDENCE_INSUFFICIENT` | Required genuine evidence; preserve any one of `RECEIVED`, `OCR_COMPLETED`, `OCR_PARTIAL`, or `OCR_FAILED` | Required actual source-bound `INSUFFICIENT` gate with nonempty recorded reasons | Null | Both null |

For either outcome carrying evidence, the response preserves the actual status,
token identities, source provenance, and request/image correlation. A status
name is not a correctness claim and must not be used to infer OCR success.

**Technical-failure stage matrix — unchanged by the R2 resolution**

| Failure stage | Allowed terminal outcome | `sourceEvidence` | Backend condition recorded for technical-failure evidence | `sourceGate` | Recorded `SUFFICIENT` permitted? | `automaticExtraction` | `receipt` |
|---|---|---|---|---|---|---|---|
| `AVAILABILITY` | `PROCESSING_UNAVAILABLE` only | Null | None; no OCR status exists | Null | No | Null | Null |
| `OCR` | `PROCESSING_FAILED` | Optional | If present, genuine `OCR_FAILED` only; `RECEIVED`, `OCR_PARTIAL`, and `OCR_COMPLETED` reject for this technical-failure stage | Null | No | Null | Null |
| `SOURCE_GATE` | `PROCESSING_FAILED` | Required | `OCR_COMPLETED` or `OCR_PARTIAL` only | Null because no durable gate result was recorded | No | Null | Null |
| `EXTRACTION` | `PROCESSING_FAILED` | Required | `OCR_COMPLETED` or `OCR_PARTIAL` only | Required recorded `SUFFICIENT` | Yes, required | Null | Null |
| `PRESENTATION_ADAPTER` | `PROCESSING_FAILED` | Required | `OCR_COMPLETED` or `OCR_PARTIAL` only | Required recorded `SUFFICIENT` | Yes, required | Null | Null |

These rows constrain technical-failure envelopes only. They do not narrow the
four evidence statuses conditionally permitted for `RESULT_AVAILABLE` or a
successfully emitted `SOURCE_EVIDENCE_INSUFFICIENT` response. A structurally
valid `ReceiptOutput` with `extractionStatus: FAILED` remains an available
result; its structural status is preserved and is not converted into an
operational failure merely because it is named `FAILED`.

### 4.1 `AVAILABILITY`

- This stage represents absence of processing capability before OCR evidence or
  a gate result exists.
- It is valid only with `PROCESSING_UNAVAILABLE`.
- Evidence, gate, automatic extraction, and receipt are all null.
- `PROCESSING_FAILED` plus `AVAILABILITY` is rejected because it duplicates the
  capability-unavailable terminal outcome.

### 4.2 `OCR`

- This stage represents a technical failure while attempting OCR, before a gate
  result is recorded.
- `sourceGate` is always null; a fabricated gate decision is forbidden.
- `sourceEvidence` may be null if no adapted summary could be produced.
- Existing fixture 07 demonstrates the proposed accepted case where a summary
  exists with `OCR_FAILED` and an empty token registry.
- No token-count minimum is introduced; Contract V0 and `AdaptedOcrSource` do
  not establish one.
- Leng approved null or genuine `OCR_FAILED` evidence only for this technical
  failure stage. `RECEIVED` and `OCR_PARTIAL` reject here.
- `OCR_COMPLETED` also rejects at this stage: after completed OCR, a
  later technical error should be classified by the later stage actually
  reached. This is presentation-stage policy, not a Contract V0 invariant.

### 4.3 `SOURCE_GATE`

- This stage represents a technical exception while attempting to produce the
  gate result.
- A pre-gate evidence summary is required.
- Leng approved `OCR_COMPLETED` or `OCR_PARTIAL` evidence only for this
  technical-failure stage. `RECEIVED` and `OCR_FAILED` reject here.
- `sourceGate` is null because no durable gate result was recorded.
- If an actual gate result exists, this stage is no longer used.

Two post-gate cases are intentionally distinct:

- **Case A — successful insufficient-evidence response:** an actual
  `INSUFFICIENT` gate was recorded and its presentation response was
  successfully constructed. The terminal outcome is
  `SOURCE_EVIDENCE_INSUFFICIENT`.
- **Case B — technical exception after insufficient gate:** an actual
  `INSUFFICIENT` gate was recorded, but subsequent backend
  presentation/projection failed. This is
  `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`. It is not a successful
  insufficient-evidence response, a `SOURCE_GATE` failure, a presently defined
  `PRESENTATION_ADAPTER` failure, `PROCESSING_UNAVAILABLE`, or a fifth outcome.

A later error after a recorded `SUFFICIENT` gate uses `EXTRACTION` or the
backend `PRESENTATION_ADAPTER` stage actually reached.

### 4.4 `EXTRACTION`

- This stage represents a technical exception while invoking the selected
  extractor after a real recorded sufficient gate.
- Evidence and a recorded `SUFFICIENT` gate are required.
- Leng approved `OCR_COMPLETED` or `OCR_PARTIAL` evidence only for this
  technical-failure stage. `RECEIVED` and `OCR_FAILED` reject here. This is a
  V1 presentation restriction, not a Contract V0 invariant.
- Automatic extraction and receipt remain null because no transportable
  `ReceiptOutput` was returned.
- If an extractor returns a valid `ReceiptOutput` whose structural status is
  `FAILED`, the terminal outcome is `RESULT_AVAILABLE`, not an extraction-stage
  technical failure.

### 4.5 `PRESENTATION_ADAPTER`

- Leng approved the definition of this stage as a backend-side projection
  failure after a valid Contract V0 `ReceiptOutput` existed.
- Evidence and a recorded `SUFFICIENT` gate are required.
- Leng approved `OCR_COMPLETED` or `OCR_PARTIAL` evidence only for this
  technical-failure stage. `RECEIVED` and `OCR_FAILED` reject here.
- The failure envelope keeps automatic extraction and receipt null; it must not
  send a partial or fabricated presentation payload.
- Android JSON decoding/semantic rejection is a local contract-validation error,
  not a backend-emitted `PRESENTATION_ADAPTER` failure.
- Leng also approved that the backend must distinguish an extraction exception
  from a presentation-adapter exception before emitting either stage. This rule
  is included in the recorded S-06 shared-owner design agreement.

## 5. Cross-outcome consistency rules

The following rules apply regardless of failure stage:

1. Every `PROCESSING_FAILED` envelope has a non-null failure object and null
   `automaticExtraction` and `receipt`.
2. `AVAILABILITY` is valid only for `PROCESSING_UNAVAILABLE`.
3. A recorded `INSUFFICIENT` gate is never carried by `PROCESSING_FAILED`. A
   successfully constructed `SOURCE_EVIDENCE_INSUFFICIENT` response requires
   genuine evidence in any of the four preserved Contract V0 statuses, an
   actual source-bound insufficient gate with nonempty recorded reasons,
   consistent request/image identities, and null failure, extraction, and
   receipt.
4. `RESULT_AVAILABLE` requires a genuine structurally valid Contract V0
   `ReceiptOutput`, genuine evidence in any of the four preserved statuses, an
   actual source-bound `SUFFICIENT` gate, automatic extraction metadata,
   receipt, consistent request/image identities, and preserved extraction
   status and original provenance. Its failure is null.
5. A gate object is emitted only when an actual gate result exists. The matrix
   never invents `SUFFICIENT`, `INSUFFICIENT`, or a gate ID.
6. Evidence is emitted only when a real adapter/evidence summary exists. A null
   summary is not replaced with fabricated OCR status or tokens.
7. When an evidence summary is present, token IDs remain unique. No
   stage-specific token-count minimum is proposed.
8. `automaticExtraction`/`receipt` are never used to carry partial data for a
   technical failure.
9. The stage-specific evidence restrictions in Section 4 apply only to
   technical `PROCESSING_FAILED` envelopes. They do not narrow the conditionally
   allowed status set for either evidence-carrying nontechnical outcome.
10. Case B, a backend projection exception after an actual recorded
    `INSUFFICIENT` gate, is `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`. It must not
    be serialized by inventing an existing outcome, stage, successful response,
    or fifth outcome.
11. Preserving `extractionStatus: FAILED` in a real Contract V0 `ReceiptOutput`
    does not itself turn an available result into a technical failure.

## 6. Leng backend decision dispositions

The first table preserves Leng's original R1 S-06 response. The second records
his separately dated R2 shared-resolution response. The third records Tai's
confirmation and Leng's subsequent acknowledgement. Together they establish the
S-06 shared-owner design agreement without approving the full V1 contract.

### 6.1 Original L-S06-01 through L-S06-08 response

| ID | Disposition | Recorded implication |
|---|---|---|
| L-S06-01 | `APPROVED` | An OCR-stage technical failure permits null evidence or genuine `OCR_FAILED` evidence only; `RECEIVED` rejects. |
| L-S06-02 | `APPROVED` | `OCR_PARTIAL` rejects at the OCR technical-failure stage. |
| L-S06-03 | `APPROVED` | `SOURCE_GATE`, `EXTRACTION`, and backend `PRESENTATION_ADAPTER` technical failures permit `OCR_COMPLETED` or `OCR_PARTIAL` evidence only. |
| L-S06-04 | `APPROVED_WITH_EXCEPTION` | Case A, an actual `INSUFFICIENT` gate with a successfully constructed response, uses `SOURCE_EVIDENCE_INSUFFICIENT`. R1 left Case B outside the approved failure envelope; L-S06-R2-03 now records it as deferred outside V1 JSON conformance. |
| L-S06-05 | `APPROVED` | `PRESENTATION_ADAPTER` means backend projection after a real `ReceiptOutput`; Android decoding or semantic rejection remains local validation. |
| L-S06-06 | `APPROVED` | The backend must distinguish an extraction exception from a presentation-adapter exception before emitting either stage. |
| L-S06-07 | `APPROVED` | V1 adds no stage-specific token-count minimum; any emitted summary preserves actual evidence. |
| L-S06-08 | `APPROVED_WITH_EXCEPTION` | The evidence restrictions apply only to technical-failure envelopes. R1 left the `RESULT_AVAILABLE` profile for `RECEIVED` or `OCR_FAILED` open; L-S06-R2-01 now resolves that backend-side question with conditions. |

### 6.2 Leng shared-resolution response — 2026-11-04

Authority: `APPROVE WITH EXCEPTIONS — S-06 SHARED RESOLUTION`.

| ID | Leng disposition | Recorded resolution | Relationship to R1 |
|---|---|---|---|
| L-S06-R2-01 | `APPROVED_WITH_CONDITIONS` | `RESULT_AVAILABLE` permits `RECEIVED`, `OCR_COMPLETED`, `OCR_PARTIAL`, or `OCR_FAILED` only with a genuine structurally valid Contract V0 `ReceiptOutput`, actual evidence, an actual source-bound `SUFFICIENT` gate, required extraction metadata and receipt, consistent request/image identities, and preserved extraction status and provenance. No status implies OCR success. | Resolves the available-result question left open by L-S06-08 without relaxing any technical-failure-stage restriction. |
| L-S06-R2-02 | `APPROVED_WITH_CONDITIONS` | `SOURCE_EVIDENCE_INSUFFICIENT` permits the same four statuses only with genuine evidence, an actual source-bound `INSUFFICIENT` gate, nonempty recorded reasons, preserved status/token identities/provenance, and null technical failure, extraction, and receipt. No status implies OCR success. | Completes the Case A evidence profile associated with L-S06-04. |
| L-S06-R2-03 | `DEFERRED` | A technical exception after an actual insufficient gate but before successful presentation construction is `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`; no V1 outcome or failure stage is assigned. | Refines Case B under L-S06-04 without adding a fifth outcome, transport envelope, HTTP status, or fallback behavior. |

### 6.3 Shared-owner confirmation — 2026-11-04

- Tai approved the reconciled L-S06-R2-01 through L-S06-R2-03 rules and the
  retained technical-failure-stage restrictions.
- Leng subsequently acknowledged and accepted Tai's confirmation without
  reopening S-06.
- Recorded state: `S06_SHARED_OWNER_DESIGN_AGREED`.

Leng's L-01 through L-07 complete-contract review, Tai's T-01 through T-07
review, and shared S-01 through S-05 and S-07 through S-11 approval remain
pending. The S-06 agreement does not substitute for those approvals or authorize
implementation.

## 7. Synthetic fixture proposal

No fixture is created or changed in this clarification. Existing fixture 06
covers availability/no evidence; existing fixture 07 covers OCR failure with an
`OCR_FAILED` summary. Proposed fixture 16 in the expansion document remains the
separate insufficient-evidence outcome.

### 7.1 Additional accepted cases

| Proposed filename | Expected result | Matrix case |
|---|---|---|
| `s06-01-ocr-failure-without-evidence.proposed.json` | `ACCEPT` | OCR failure before an evidence summary exists; gate/output null |
| `s06-02-source-gate-failure-after-completed-ocr.proposed.json` | `ACCEPT` | Completed evidence, gate technical failure, no recorded gate |
| `s06-03-source-gate-failure-after-partial-ocr.proposed.json` | `ACCEPT` | Partial evidence, gate technical failure, no recorded gate |
| `s06-04-extraction-failure-after-completed-ocr-and-sufficient-gate.proposed.json` | `ACCEPT` | Completed evidence and real sufficient gate; output null |
| `s06-05-extraction-failure-after-partial-ocr-and-sufficient-gate.proposed.json` | `ACCEPT` | Partial evidence and real sufficient gate; output null |
| `s06-06-presentation-adapter-failure-after-completed-ocr.proposed.json` | `ACCEPT` | Completed evidence and sufficient gate; projection fails |
| `s06-07-presentation-adapter-failure-after-partial-ocr.proposed.json` | `ACCEPT` | Partial evidence and sufficient gate; projection fails |

No accepted technical-failure fixture may pair the OCR stage with `RECEIVED` or
`OCR_PARTIAL`, or any later technical-failure stage with `RECEIVED` or
`OCR_FAILED`, under the recorded backend conditions.

### 7.2 Additional rejected cases

| Proposed filename | Proposed rejection | Single inconsistency |
|---|---|---|
| `s06-08-processing-failed-at-availability.proposed.json` | `REJECT_OUTCOME_STAGE_MISMATCH` | `PROCESSING_FAILED` incorrectly uses `AVAILABILITY` |
| `s06-09-unavailable-with-source-evidence.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Capability-unavailable outcome carries evidence |
| `s06-10-unavailable-with-gate.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Capability-unavailable outcome carries gate |
| `s06-11-ocr-failure-with-sufficient-gate.proposed.json` | `REJECT_GATE_STAGE_MISMATCH` | OCR-stage failure carries recorded gate |
| `s06-12-ocr-failure-with-completed-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Completed OCR is paired with OCR-stage failure |
| `s06-13-source-gate-failure-without-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Gate-stage failure lacks pre-gate evidence summary |
| `s06-14-source-gate-failure-with-recorded-sufficient-gate.proposed.json` | `REJECT_GATE_STAGE_MISMATCH` | Durable sufficient gate already exists |
| `s06-15-source-gate-failure-with-recorded-insufficient-gate.proposed.json` | `REJECT_GATE_OUTCOME_MISMATCH` | Recorded insufficient decision uses technical-failure outcome |
| `s06-16-extraction-failure-without-gate.proposed.json` | `REJECT_GATE_STAGE_MISMATCH` | Extraction-stage failure lacks sufficient gate |
| `s06-17-extraction-failure-with-insufficient-gate.proposed.json` | `REJECT_GATE_OUTCOME_MISMATCH` | Insufficient decision uses extraction failure |
| `s06-18-extraction-failure-with-ocr-failed-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Recorded backend condition excludes OCR-failed evidence from this technical-failure stage |
| `s06-19-presentation-adapter-failure-without-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Adapter-stage failure lacks evidence summary |
| `s06-20-presentation-adapter-failure-without-gate.proposed.json` | `REJECT_GATE_STAGE_MISMATCH` | Adapter-stage failure lacks sufficient gate |
| `s06-21-presentation-adapter-failure-with-insufficient-gate.proposed.json` | `REJECT_GATE_OUTCOME_MISMATCH` | Insufficient decision uses adapter failure |
| `s06-22-processing-failure-with-extraction-payload.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Technical failure carries automatic extraction metadata |
| `s06-23-processing-failure-with-receipt.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Technical failure carries receipt |
| `s06-24-processing-failure-with-insufficient-gate.proposed.json` | `REJECT_GATE_OUTCOME_MISMATCH` | Any failed stage carries an insufficient gate |
| `s06-25-unknown-failure-stage.proposed.json` | `REJECT_UNKNOWN_ENUM` | Failure stage is outside the five-stage presentation enum |
| `s06-26-ocr-failure-with-received-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | OCR technical failure carries `RECEIVED` evidence |
| `s06-27-ocr-failure-with-partial-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | OCR technical failure carries `OCR_PARTIAL` evidence |
| `s06-28-source-gate-failure-with-received-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Source-gate technical failure carries `RECEIVED` evidence |
| `s06-29-source-gate-failure-with-ocr-failed-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Source-gate technical failure carries `OCR_FAILED` evidence |
| `s06-30-extraction-failure-with-received-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Extraction technical failure carries `RECEIVED` evidence |
| `s06-31-presentation-adapter-failure-with-received-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Backend adapter technical failure carries `RECEIVED` evidence |
| `s06-32-presentation-adapter-failure-with-ocr-failed-evidence.proposed.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | Backend adapter technical failure carries `OCR_FAILED` evidence |

The rejection proposals involving a recorded `INSUFFICIENT` gate reject an
attempted, contradictory V1 JSON envelope. They do not define how Case B is
transported or reported after envelope construction itself fails.

### 7.3 Resolved outcome cases and deferred lifecycle

- `67-result-with-ocr-failed-evidence.proposed.json` and
  `67a-result-with-received-evidence.proposed.json` are proposed `ACCEPT` cases
  only when each is constructed from a genuine structurally valid synthetic
  Contract V0 `ReceiptOutput` and satisfies every available-result condition.
- Proposed fixtures 75 through 77 give successful insufficient-evidence
  responses individual coverage for `OCR_PARTIAL`, `RECEIVED`, and `OCR_FAILED`;
  fixture 16 is clarified as the `OCR_COMPLETED` case. Each requires genuine
  evidence and an actual source-bound insufficient gate with nonempty reasons.
- `lifecycle-s06-insufficient-gate-then-projection-exception` is a non-JSON
  lifecycle/test-plan scenario with status
  `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`. It has no V1 `ACCEPT`/`REJECT`
  expectation and must not contain a fabricated response envelope.

## 8. Recorded shared-owner wording for S-06

The following wording is the recorded S-06 shared-owner design agreement:

> `receipt-presentation-v1` retains four terminal outcomes:
> `RESULT_AVAILABLE`, `PROCESSING_UNAVAILABLE`, `PROCESSING_FAILED`, and
> `SOURCE_EVIDENCE_INSUFFICIENT`. `RESULT_AVAILABLE` may preserve any one of
> `RECEIVED`, `OCR_COMPLETED`, `OCR_PARTIAL`, or `OCR_FAILED` only when a genuine
> structurally valid Contract V0 `ReceiptOutput`, actual evidence, an actual
> source-bound `SUFFICIENT` gate, required automatic extraction metadata and
> receipt, consistent request/image identities, and original extraction status
> and provenance are present. A preserved `extractionStatus: FAILED` does not
> become an operational failure merely because of its name. A successfully
> emitted `SOURCE_EVIDENCE_INSUFFICIENT` response may preserve the same four
> statuses only with genuine evidence, an actual source-bound `INSUFFICIENT`
> gate with nonempty recorded reasons, preserved token identities/provenance,
> and null technical failure, extraction, and receipt. No source-processing
> status implies OCR success. `PROCESSING_UNAVAILABLE` alone uses
> `AVAILABILITY`. Technical `PROCESSING_FAILED` envelopes permit `OCR`,
> `SOURCE_GATE`, `EXTRACTION`, and `PRESENTATION_ADAPTER`; they contain a failure
> object and null automatic extraction and receipt. OCR-stage failure permits
> null or genuine `OCR_FAILED` evidence and no gate. Source-gate-stage failure
> requires `OCR_COMPLETED` or `OCR_PARTIAL` evidence and no recorded gate.
> Extraction and backend presentation-adapter failures require `OCR_COMPLETED`
> or `OCR_PARTIAL` evidence plus a recorded `SUFFICIENT` gate. These narrower
> technical-failure restrictions remain unchanged. A technical exception after
> an actual insufficient gate but before successful presentation construction
> is `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`; it is not assigned a V1 outcome
> or stage. No adapter may invent evidence, gate decisions, extraction output,
> receipt content, or a fifth terminal outcome.

This wording records Leng's L-S06-01 through L-S06-08 response, his dated
L-S06-R2-01 through L-S06-R2-03 resolution, Tai's confirmation, and Leng's
subsequent acknowledgement. S-06 is agreed; all other owner and shared decisions
remain subject to the consolidated M3D-1 approval package.

## Classification

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_FULL_CONTRACT_APPROVAL_PENDING`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
