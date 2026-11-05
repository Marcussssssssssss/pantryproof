# M3D-1 Tai Independent Review

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

**Owner:** Tai Yong Xin  
**Approval candidate:** `M3D-1-APPROVAL-CANDIDATE-2026-11-04`  
**Register:** `m3d-1-consolidated-approval-register.md`  
**Initial state:** `PENDING_TAI_REVIEW`  
**Previously agreed:** `S06_SHARED_OWNER_DESIGN_AGREED`

## Instructions

Review the exact approval candidate identified above. For every row, retain
`APPROVE` or replace the response with `EXCEPTION` plus the exact required
wording. Every row is initially pending; blank or ambiguous responses are not
approval.

S-06 is already jointly agreed and is not reopened here. This review excludes
OCR orchestration, runtime packaging, persistence, evaluation, live producer
selection, and deferred post-insufficient transport/error handling.

## Tai decisions T-01 through T-07

| ID | Existing recommended choice | One-sentence rationale | Response — initially `PENDING` |
|---|---|---|---|
| T-01 | Accept the primitive JSON shape as API-26 feasible; require duplicate-key-aware strict decoding, `BigDecimal` for money/quantity, strict `LocalDate`, and finite `Double` only for native confidence; parser library remains an implementation choice. | The transport is language-neutral and requires no Android/Python type tags. | `APPROVE / EXCEPTION: ____________________` |
| T-02 | Use a new immutable automatic-result DTO; never force incomplete fields or decimal quantities into the current typed `Receipt`. | Current Android models cannot losslessly represent missing/unresolved fields or weighted quantities. | `APPROVE / EXCEPTION: ____________________` |
| T-03 | Derive a separate editable string draft while retaining the immutable envelope, identities, statuses, reasons, values, tokens, source, gate, extraction status, and producer. | Manual review must not destroy automatic provenance. | `APPROVE / EXCEPTION: ____________________` |
| T-04 | Keep the existing synthetic demo outside this contract; failed, unavailable, insufficient, malformed, or stale local results must never display mock fields as extracted. | This preserves truthful local-image versus synthetic-source labeling. | `APPROVE / EXCEPTION: ____________________` |
| T-05 | Map `UNIT_PRICE/MISSING` to a blank optional nonblocking field; keep `UNRESOLVED` visibly unresolved; never fill either from external reference evidence. | This preserves current optional-unit-price UX without a correctness claim. | `APPROVE / EXCEPTION: ____________________` |
| T-06 | Preserve quantity as an exact positive canonical decimal with scale at most three; never round or feed it into the integer 0–99 inventory model automatically. | Receipt weight and household inventory count are separate domains. | `APPROVE / EXCEPTION: ____________________` |
| T-07 | Reject unsupported versions and malformed states before UI mapping; keep failure stage closed, failure code syntactically open, and use a localized generic fallback. | This prevents silent schema drift while permitting backend diagnostic growth. | `APPROVE / EXCEPTION: ____________________` |

## Remaining shared decisions

| ID | Existing recommended choice | One-sentence rationale | Response — initially `PENDING` |
|---|---|---|---|
| S-01 | Keep immutable `originalAutomaticValue` and deterministic `presentationValue`; permit only defined money-prefix/grouping removal, never correction, rounding, arithmetic, or text/date/quantity changes. | This provides Android-ready values without hiding or rewriting Contract V0 output. | `APPROVE / EXCEPTION: ____________________` |
| S-02 | Require `currencyCode: "MYR"`; money uses exactly two fractional digits and is nonnegative; quantity is positive plain decimal with scale zero to three; date is Gregorian-valid ISO; reject signs, exponents, unsupported locale/grouping forms, NaN/infinity, and rounding. | Exact shared grammars prevent Kotlin/Python interpretation drift and false RM formatting. | `APPROVE / EXCEPTION: ____________________` |
| S-03 | Treat JSON array order as normative with exact receipt/item role order and source item-row order; do not add `rowIndex`. | This follows Contract V0 tuple order without creating contradictory order fields. | `APPROVE / EXCEPTION: ____________________` |
| S-04 | Use case-sensitive opaque IDs/reference grammar `[A-Za-z0-9][A-Za-z0-9._-]*`; require uniqueness and caller-supplied request/image correlation; prohibit paths, URIs, whitespace, participant/evaluation identities, and receipt content. | Out-of-envelope correlation prevents stale-image attribution without exposing device-local identifiers. | `APPROVE / EXCEPTION: ____________________` |
| S-05 | Permit `LOCAL_IMAGE` and fixture-only `SYNTHETIC_FIXTURE`; accept synthetic sources only in fixture mode; make SHA-256 null or 64 lowercase hex while deferring production digest population. | This fixes syntax and fixture isolation while retaining a separate privacy choice. | `APPROVE / EXCEPTION: ____________________` |
| S-07 | Reject unknown members at every wrapper/envelope object level and duplicate keys lexically; require a new schema version for additive members while keeping failure codes open strings. | Fail-closed V1 gives Kotlin and Python identical parsing behavior. | `APPROVE / EXCEPTION: ____________________` |
| S-08 | Preserve `ReceiptOutput.extraction_status` exactly and validate only enum membership; do not recompute B1/B2 completeness in presentation validators. | Recalculation would import producer behavior not enforced by Contract V0 and risk cross-runtime drift. | `APPROVE / EXCEPTION: ____________________` |
| S-09 | Enforce the recorded missing/unresolved/extracted value, reason, token, and finite-confidence rules; Python validates projected token IDs against full immutable evidence, while Kotlin validates only projected reference integrity; defer reason codes. | This preserves incomplete states without overstating Android's ability to authenticate omitted OCR evidence. | `APPROVE / EXCEPTION: ____________________` |
| S-10 | Omit external unit-price reference evidence from V1; absence says nothing about availability and must not fill, validate, or imply correctness of extracted `UNIT_PRICE`. | Contract V0 keeps external reference evidence separate and does not bind it to item rows here. | `APPROVE / EXCEPTION: ____________________` |
| S-11 | Keep `producerId` opaque and case-sensitive and `producerVersion` required/nonblank; do not make producer ID a closed B1/B2/B3 enum. | This preserves traceability without selecting or coupling to a research producer. | `APPROVE / EXCEPTION: ____________________` |

## Ready-to-copy Tai response

> I, Tai Yong Xin, independently reviewed approval candidate
> `M3D-1-APPROVAL-CANDIDATE-2026-11-04` and its consolidated register. I record
> my responses to T-01 through T-07 and remaining shared decisions S-01 through
> S-05 and S-07 through S-11 as marked in this questionnaire. I acknowledge the
> previously recorded S-06 shared-owner design agreement without reopening it.
> My explicit exceptions, if any, are: `[none or list exact IDs and required
> wording]`. This response does not authorize Kotlin/Python implementation, OCR,
> backend activation, runtime integration, persistence, scoring, calibration,
> evaluation, or real-receipt processing.

**Tai name/date:** `________________________________________`

## Classification

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_FULL_CONTRACT_APPROVAL_PENDING`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
