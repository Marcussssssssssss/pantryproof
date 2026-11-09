# M3D-1 Consolidated Contract Approval Register

`M3D_CONTRACT_DESIGN_JOINTLY_APPROVED`

**Approval candidate:** `M3D-1-APPROVAL-CANDIDATE-2026-11-04`  
**Parent package:** `M3D-0R-PROPOSAL-2026-11-04`  
**Owners:** Tai Yong Xin and Leng Wei Heng  
**Date:** 2026-11-04  
**State:** `M3D_CONTRACT_DESIGN_JOINTLY_APPROVED`  
**Recorded shared decision:** `S06_SHARED_OWNER_DESIGN_AGREED`  
**M3D-2 closure record:** `m3d-2-joint-design-closure.md`  
**M3D-2 closure state:** `M3D_CONTRACT_DESIGN_JOINTLY_APPROVED`

## 1. Purpose and authority

This register binds Tai's and Leng's completed independent reviews to one exact
design candidate and five-file manifest. It records the completed S-06 shared
design agreement and the no-exception joint contract-design closure established
in `m3d-2-joint-design-closure.md`.

It does not authorize fixture creation, Kotlin/Python implementation, OCR or
source-gate orchestration, runtime packaging, backend activation, persistence,
inventory synchronization, correction, scoring, calibration, evaluation, or
real-receipt processing.

## 2. Authoritative input manifest

| Input | SHA-256 | Role in this candidate |
|---|---|---|
| `receipt-presentation-v1-draft.md` | `1E56F3C82716E889E46DEEE898233C2C143FDD6122F715A1C8E32EADCCCB01E5` | Historical base proposal; later closure text controls where refined |
| `shared-decision-register.md` | `5C3284D54C604CC71293DDC4FD3EB87E2B8099A38DF4CA9A915403BB667DBB16` | Owner/shared decision inventory with S-06 recorded agreed |
| `contract-closure-proposal.md` | `A3FD591589D9433EBA4C2F64743E0353E19978915AAE9BF1ACFE6F0E4B9F8EEC` | Exact current recommendations for remaining decisions |
| `fixture-expansion-proposal.md` | `D7E40604AE3DC67FE291414AC817739F2B05DA9CE334C1D7379536FB1CA71293` | Conditional synthetic conformance expectations |
| `s06-failure-stage-clarification.md` | `003D4348924EE5A5D54B1EE9354EA36DFC4DDEE29FF46FFB3DB6966BFE904269` | Controlling S-06 shared-owner agreement |

Precedence is narrow: the S-06 clarification controls S-06; the closure proposal
controls its explicit refinements of older open-choice wording; otherwise the
base proposal remains the design source. The two owner questionnaires reference
this same approval-candidate ID and manifest.

## 3. Recorded S-06 shared-owner design agreement

Tai approved the reconciled S-06 R2 rules, and Leng subsequently acknowledged
and accepted that confirmation. S-06 is not a remaining questionnaire item.

| Decision | Agreed design |
|---|---|
| L-S06-R2-01 | `RESULT_AVAILABLE` conditionally permits `RECEIVED`, `OCR_COMPLETED`, `OCR_PARTIAL`, or `OCR_FAILED` only with genuine valid Contract V0 output/evidence, an actual source-bound `SUFFICIENT` gate, required metadata and receipt, consistent identities, and preserved provenance/status. |
| L-S06-R2-02 | `SOURCE_EVIDENCE_INSUFFICIENT` conditionally permits the same four statuses only with genuine evidence, an actual source-bound `INSUFFICIENT` gate, nonempty recorded reasons, preserved tokens/provenance, and null failure/extraction/receipt. |
| L-S06-R2-03 | A post-insufficient-gate presentation-construction failure is `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`; it has no V1 outcome, stage, response envelope, or fallback. |

All L-S06-01 through L-S06-08 technical-failure-stage restrictions remain part
of the agreement. Conditional fixture expectations 16, 67, 67a, and 75 through
81 remain as specified; fixture bytes are not created by this approval package.

## 4. Tai-owned decisions

| ID | Approval point | Status |
|---|---|---|
| T-01 | API 26 strict DTO/JSON parsing feasibility | `APPROVED_BY_TAI` |
| T-02 | Immutable incomplete automatic-result representation | `APPROVED_BY_TAI` |
| T-03 | Provenance-preserving Manual Review mapping | `APPROVED_BY_TAI` |
| T-04 | Local-image and synthetic-demo isolation | `APPROVED_BY_TAI` |
| T-05 | Missing optional versus unresolved unit price | `APPROVED_BY_TAI` |
| T-06 | Decimal receipt quantity versus integer inventory | `APPROVED_BY_TAI` |
| T-07 | Version, malformed-state, and failure-code UI behavior | `APPROVED_BY_TAI` |

Exact choices are in `m3d-1-tai-review.md`; executed approval evidence is in
`owner-approvals/tai-m3d-1-owner-approval.md`.

## 5. Leng-owned decisions

| ID | Approval point | Status |
|---|---|---|
| L-01 | Contract V0 presentation projection boundary | `APPROVED_BY_LENG` |
| L-02 | Deterministic dedicated product projection | `APPROVED_BY_LENG` |
| L-03 | Stable identities and external request/image correlation | `APPROVED_BY_LENG` |
| L-04 | Backend evidence validation versus projected reference integrity | `APPROVED_BY_LENG` |
| L-05 | Original/canonical value preservation without correction | `APPROVED_BY_LENG` |
| L-06 | Actual gate/provenance emission and privacy redaction | `APPROVED_BY_LENG` |
| L-07 | Opaque producer/version and open failure-code metadata | `APPROVED_BY_LENG` |

Exact choices are in `m3d-1-leng-review.md`; executed approval evidence is in
`owner-approvals/leng-m3d-1-owner-approval.md`.

## 6. Shared decision register

| ID | Current recommended choice | Status |
|---|---|---|
| S-01 | Keep immutable original and deterministic presentation values; permit only the specified lexical money normalization and no correction, rounding, arithmetic, or text/date/quantity change. | `APPROVED_BY_BOTH_OWNERS` |
| S-02 | Require `MYR`; money has exactly two fractional digits; quantity is positive plain decimal with maximum scale three; date is valid ISO; reject unsupported numeric forms and rounding. | `APPROVED_BY_BOTH_OWNERS` |
| S-03 | Make array order normative with exact receipt/item role order and source row order; add no redundant row index. | `APPROVED_BY_BOTH_OWNERS` |
| S-04 | Use case-sensitive privacy-safe opaque IDs, uniqueness and caller correlation; prohibit paths, URIs, content, participant IDs, and evaluation IDs. | `APPROVED_BY_BOTH_OWNERS` |
| S-05 | Permit `LOCAL_IMAGE` and fixture-only `SYNTHETIC_FIXTURE`; digest is null or 64 lowercase hex; production digest population remains deferred. | `APPROVED_BY_BOTH_OWNERS` |
| S-06 | Four terminal outcomes, agreed outcome/evidence profiles, retained technical-failure matrix, and deferred post-insufficient construction failure. | `S06_SHARED_OWNER_DESIGN_AGREED` |
| S-07 | Reject unknown members and duplicate keys; additive members require a new schema version. | `APPROVED_BY_BOTH_OWNERS` |
| S-08 | Preserve Contract V0 extraction status exactly; do not recompute producer completeness in presentation validators. | `APPROVED_BY_BOTH_OWNERS` |
| S-09 | Enforce field-state/token/confidence rules; backend validates token IDs against full evidence while Android validates projected reference integrity; reason codes remain deferred. | `APPROVED_BY_BOTH_OWNERS` |
| S-10 | Omit external unit-price reference evidence from V1 and make no availability or correctness inference. | `APPROVED_BY_BOTH_OWNERS` |
| S-11 | Keep producer ID opaque/case-sensitive and producer version required; do not close the ID to B1/B2/B3. | `APPROVED_BY_BOTH_OWNERS` |

## 7. Remaining exclusions and future boundaries

No internal design contradiction or unresolved owner exception remains within
the M3D-1 contract-design approval scope. Tai and Leng independently approved
their seven owner decisions, independently approved all ten remaining shared
decisions, reaffirmed S-06, and declared no exceptions.

The following remain deliberately outside this approval: executable OCR,
runtime packaging, live producer selection, post-insufficient transport/error
handling, persistence, review writeback, inventory synchronization, scoring,
calibration, evaluation, and real receipt data.

## 8. Approval evidence and recording rule

Silence, file presence, a conversational summary, or approval by only one owner
does not approve the full contract. M3D-2 closure was recorded only after both
executed statements were supplied, preserved, mapped to the same candidate and
manifest, and found to contain no exceptions.

The evidence records are:

- `owner-approvals/tai-m3d-1-owner-approval.md`, SHA-256
  `23195D3DF9AFB06B83A5797984C9843358F89EF5E7B1E07FFB978BF4B5AEF39D`.
- `owner-approvals/leng-m3d-1-owner-approval.md`, SHA-256
  `34F75D6F0CC9C2BCF4EEF174CD10481032D07E9A48E35E97A0F5BE53A1D1DAFF`.

The owner-authored dates were not stated. The records preserve textual
attribution supplied through M3D-2E and do not claim independent signature or
identity authentication. The five authoritative manifest hashes were reproduced
exactly before `m3d-2-joint-design-closure.md` recorded joint design approval.

## Classification

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_CONTRACT_DESIGN_JOINTLY_APPROVED`

`SYNTHETIC_CONFORMANCE_IMPLEMENTATION_NOT_YET_AUTHORIZED`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
