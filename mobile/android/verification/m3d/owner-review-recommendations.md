# Receipt Presentation V1 — Owner Review Recommendations

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

**Package ID:** `M3D-0R-PROPOSAL-2026-11-04`  
**Approval candidate:** `M3D-1-APPROVAL-CANDIDATE-2026-11-04`  
**Decision state:** `NO_COMPLETE_OWNER_OR_JOINT_APPROVAL_RECORDED`  
**Recorded shared decision:** `S06_SHARED_OWNER_DESIGN_AGREED`

This document gives Tai and Leng concise independent-review sections. The T-01
through T-07 and L-01 through L-07 rows remain proposals, and their `Status`
columns remain pending until the named owner records a complete explicit
response. The separate S-06 tables below record only Leng's supplied backend
subdecisions, dated shared-resolution response, Tai's confirmation, and Leng's
subsequent acknowledgement. S-06 is agreed, but the full contract is not.

## 1. Tai review — T-01 through T-07

| ID | Recommended Android disposition | Rationale | Status |
|---|---|---|---|
| T-01 | Accept the primitive JSON shape as API-26 feasible. Require a strict decoder capable of duplicate-key detection; use `BigDecimal` for money/quantity, strict `LocalDate` for dates, and finite `Double` only for native confidence. Parser library remains an implementation choice. | The shape is library-neutral and contains no Android/Python type tag. | `PENDING_TAI` |
| T-02 | Keep automatic results in a new immutable DTO; never force incomplete fields or decimal quantities into the current typed `Receipt`. | Current Android models cannot represent required missing/unresolved fields or weighted quantity losslessly. | `PENDING_TAI` |
| T-03 | Derive a separate editable string draft. Retain the original envelope, IDs, statuses, reasons, values, tokens, source, gate, extraction status, and producer unchanged. | Manual editing must not erase or overwrite automatic provenance. | `PENDING_TAI` |
| T-04 | Keep existing synthetic demo behavior outside this contract. A failed, unavailable, insufficient, malformed, or stale local result must never expose mock fields as extracted. | Preserves the current truthful local-image/synthetic boundary. | `PENDING_TAI` |
| T-05 | Map `UNIT_PRICE/MISSING` to a blank optional field and keep it nonblocking. Show `UNIT_PRICE/UNRESOLVED` as unresolved and requiring attention. Never populate either from external reference evidence. | Matches current optional unit-price UX without a correctness claim. | `PENDING_TAI` |
| T-06 | Preserve receipt quantity as an exact positive canonical decimal with maximum scale three. Never round, and do not change or automatically feed the integer 0-99 inventory model. | Weighted receipt quantity and household stock count are different domains. | `PENDING_TAI` |
| T-07 | Reject unsupported versions and malformed states before UI mapping. Keep failure stage closed, failure code open under its token grammar, and use a generic localized fallback for unknown codes. | Prevents silent schema drift while permitting backend diagnostic growth. | `PENDING_TAI` |

### Proposed Tai approval statement

Tai may use the following only after independently checking the package and
listing any exceptions:

> I, Tai Yong Xin, have independently reviewed approval candidate
> `M3D-1-APPROVAL-CANDIDATE-2026-11-04` and its consolidated register. I approve
> the T-01 through T-07 recommendations and record my responses to remaining
> shared decisions S-01 through S-05 and S-07 through S-11. I acknowledge the
> recorded S-06 shared-owner design agreement without reopening it. I confirm
> that the proposed shape is feasible for an API 26 Kotlin consumer; incomplete automatic
> data remains outside the current typed `Receipt`; the synthetic demo remains
> isolated; missing optional unit price remains nonblocking; and decimal receipt
> quantity does not alter integer inventory semantics. My explicit exceptions,
> if any, are: `[none or list exact T/S IDs and required wording]`. This approval
> does not authorize implementation, OCR, backend activation, persistence,
> scoring, evaluation, or real receipt data.

If Tai lists an exception, the affected item remains pending until both owners
approve revised wording and fixtures. The statement must be dated and retained
with the package revision it names.

## 2. Leng review — L-01 through L-07

| ID | Recommended backend disposition | Rationale | Status |
|---|---|---|---|
| L-01 | Treat V1 as a presentation projection, not a lossless Contract V0 serialization. Preserve the seven roles, field states, exact original values/reasons/confidence, identities, token references, gate, extraction status, producer version, and `PRE_REVIEW_AUTOMATIC`. Validate omitted redundant receipt/row relationships before projection. | Avoids redefining Contract V0 while permitting a minimal privacy-aware transport. | `PENDING_LENG` |
| L-02 | Use a dedicated future product projector; do not reuse proposed-method serialization. Semantic acceptance ignores object-property order but preserves array order and rejects duplicate keys. | Proposed-method JSON is not a product receipt interface. | `PENDING_LENG` |
| L-03 | Require exact case-sensitive IDs, receipt-wide unique fields, unique rows/tokens, and caller-supplied expected request/image context. | JSON alone cannot detect a stale but internally valid response. | `PENDING_LENG` |
| L-04 | Treat the projected token registry as reference integrity only. Before emission, validate it against full immutable Contract V0 OCR evidence; never describe Android's token checks as evidence authenticity. | Android intentionally receives no OCR text or geometry. | `PENDING_LENG` |
| L-05 | Retain original and canonical values. Permit only the approved role-specific lexical normalization; never round, repair, recompute totals, or change a Contract V0 field status to make projection succeed. | Prevents presentation mapping from becoming hidden correction logic. | `PENDING_LENG` |
| L-06 | Emit a gate only from an actual recorded result. Available output requires `SUFFICIENT`; insufficient evidence uses its separate terminal outcome. Redact paths, URIs, receipt text, participant IDs, and evaluation references. | Preserves source-gate meaning and local-first privacy. | `PENDING_LENG` |
| L-07 | Keep producer ID opaque and producer version required. Keep failure codes open under a syntax rule, and do not select B1/B2/B3 in this contract review. | Provides traceability without coupling or methodology selection. | `PENDING_LENG` |

### Recorded S-06 backend subdecisions — not complete Leng approval

| ID | Leng disposition | Recorded implication |
|---|---|---|
| L-S06-01 | `APPROVED` | OCR technical failure permits null or genuine `OCR_FAILED` evidence only. |
| L-S06-02 | `APPROVED` | `OCR_PARTIAL` rejects at the OCR technical-failure stage. |
| L-S06-03 | `APPROVED` | Source-gate and later technical failures permit `OCR_COMPLETED` or `OCR_PARTIAL` evidence only. |
| L-S06-04 | `APPROVED_WITH_EXCEPTION` | A successfully constructed response after an actual `INSUFFICIENT` gate uses `SOURCE_EVIDENCE_INSUFFICIENT`; R1 left a later projection exception outside the approved failure envelope. |
| L-S06-05 | `APPROVED` | Backend `PRESENTATION_ADAPTER` is projection after a real `ReceiptOutput`; Android rejection remains local. |
| L-S06-06 | `APPROVED` | Backend emission must distinguish extraction from presentation-adapter exceptions. |
| L-S06-07 | `APPROVED` | No stage-specific token minimum is introduced. |
| L-S06-08 | `APPROVED_WITH_EXCEPTION` | Technical-failure restrictions do not settle `RESULT_AVAILABLE` with `RECEIVED` or `OCR_FAILED`; R1 required a separate shared decision. |

### Leng S-06 shared-resolution response — 2026-11-04

Authority: `APPROVE WITH EXCEPTIONS — S-06 SHARED RESOLUTION`.

| ID | Leng disposition | Recorded resolution | Relationship to original exception |
|---|---|---|---|
| L-S06-R2-01 | `APPROVED_WITH_CONDITIONS` | `RESULT_AVAILABLE` permits all four Contract V0 evidence statuses only with genuine output/evidence, an actual source-bound sufficient gate, required metadata and receipt, matching request/image identities, and preserved extraction status/provenance. | Resolves Leng's available-result evidence question under L-S06-08 without relaxing technical-failure restrictions. |
| L-S06-R2-02 | `APPROVED_WITH_CONDITIONS` | `SOURCE_EVIDENCE_INSUFFICIENT` permits all four statuses only with genuine evidence, an actual source-bound insufficient gate, nonempty recorded reasons, preserved status/tokens/provenance, and null failure/extraction/receipt. | Completes the successfully emitted Case A profile associated with L-S06-04; no status implies OCR success. |
| L-S06-R2-03 | `DEFERRED` | A post-insufficient-gate presentation-construction exception is `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`, with no assigned outcome, stage, response envelope, HTTP behavior, or fallback. | Carries Case B under L-S06-04 into a later transport/error-handling design without inventing a fifth outcome. |

### Recorded S-06 shared-owner agreement — 2026-11-04

Tai approved the reconciled L-S06-R2-01 through L-S06-R2-03 rules and retained
technical-failure restrictions. Leng subsequently acknowledged and accepted
that confirmation. The recorded state is `S06_SHARED_OWNER_DESIGN_AGREED`.

Leng's L-01 through L-07 review, Tai's T-01 through T-07 review, and shared
S-01 through S-05 and S-07 through S-11 approval remain pending. Nothing
recorded here authorizes implementation or constitutes full-contract approval.

### Proposed Leng approval statement

Leng may use the following only after independently checking the package and
listing any exceptions:

> I, Leng Wei Heng, have independently reviewed approval candidate
> `M3D-1-APPROVAL-CANDIDATE-2026-11-04` and its consolidated register. I approve
> the L-01 through L-07 recommendations and record my responses to remaining
> shared decisions S-01 through S-05 and S-07 through S-11. I acknowledge the
> recorded S-06 shared-owner design agreement without reopening it. I confirm
> that this is a presentation projection rather than a lossless Contract V0 serialization;
> it does not alter Contract V0, B1/B2/B3, proposed-method, or evaluation
> semantics. My explicit exceptions, if any, are: `[none or list exact L/S IDs
> and required wording]`. This approval does not authorize implementation, OCR
> orchestration, real-receipt processing, runtime integration, persistence,
> scoring, calibration, evaluation, or backend activation.

If Leng lists an exception, the affected item remains pending until both owners
approve revised wording and fixtures. The statement must be dated and retained
with the package revision it names.

## 3. Joint closure statement after both independent reviews

This statement is not effective until both individual reviews are explicit and
all exceptions are reconciled:

> We, Tai Yong Xin and Leng Wei Heng, jointly approve the remaining S-01 through
> S-05 and S-07 through S-11 dispositions in approval candidate
> `M3D-1-APPROVAL-CANDIDATE-2026-11-04`, and acknowledge the previously recorded
> S-06 shared-owner design agreement without reopening it. We approve creation
> of a frozen successor fixture set incorporating the listed updates and additions.
> This closure may support a future separately authorized synthetic-only
> projector/validator milestone. It does not authorize OCR orchestration,
> production producer selection, Android/backend activation, persistence,
> scoring, calibration, evaluation, or real receipt data.

Until those responses exist, classifications remain:

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_FULL_CONTRACT_APPROVAL_PENDING`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
