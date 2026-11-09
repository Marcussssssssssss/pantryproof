# M3D-1 Leng Independent Review

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

**Owner:** Leng Wei Heng  
**Approval candidate:** `M3D-1-APPROVAL-CANDIDATE-2026-11-04`  
**Register:** `m3d-1-consolidated-approval-register.md`  
**Initial state:** `PENDING_LENG_REVIEW`  
**Previously agreed:** `S06_SHARED_OWNER_DESIGN_AGREED`

## Instructions

Review the exact approval candidate identified above. For every row, retain
`APPROVE` or replace the response with `EXCEPTION` plus the exact required
wording. Every row is initially pending; blank or ambiguous responses are not
approval.

S-06 is already jointly agreed and is not reopened here. This review excludes
OCR orchestration, runtime packaging, persistence, evaluation, live producer
selection, and deferred post-insufficient transport/error handling.

## Leng decisions L-01 through L-07

| ID | Existing recommended choice | One-sentence rationale | Response — initially `PENDING` |
|---|---|---|---|
| L-01 | Treat V1 as a presentation projection, not a lossless Contract V0 serialization; preserve seven roles, field states, exact original values/reasons/confidence, identities, token references, gate, extraction status, producer version, and `PRE_REVIEW_AUTOMATIC`, validating omitted containment relationships before projection. | This preserves Contract V0 meaning while allowing a minimal privacy-safe transport. | `APPROVE / EXCEPTION: ____________________` |
| L-02 | Use a dedicated future product projector, not proposed-method/evaluation serialization; ignore object-property order semantically, preserve array order, and reject duplicate keys. | Product transport must be deterministic without coupling to research serializers. | `APPROVE / EXCEPTION: ____________________` |
| L-03 | Require exact case-sensitive IDs, receipt-wide unique fields, unique rows/tokens, and caller-supplied expected request/image context. | Internal JSON validity alone cannot detect a stale or misattributed response. | `APPROVE / EXCEPTION: ____________________` |
| L-04 | Treat projected token IDs as reference integrity only; before emission, validate them against full immutable Contract V0 OCR evidence, and never call Android token checks evidence authenticity. | Android intentionally receives no OCR text or geometry and cannot prove evidence authenticity itself. | `APPROVE / EXCEPTION: ____________________` |
| L-05 | Retain original and canonical values; allow only approved lexical normalization and never round, repair, recompute totals, or change field status to make projection pass. | This prevents the presentation adapter from becoming hidden correction logic. | `APPROVE / EXCEPTION: ____________________` |
| L-06 | Emit only actual recorded gates; require `SUFFICIENT` for available output, use the separate insufficient outcome for `INSUFFICIENT`, and redact paths, URIs, receipt text, participant IDs, and evaluation references. | This preserves source-gate semantics and local-first privacy. | `APPROVE / EXCEPTION: ____________________` |
| L-07 | Keep `producerId` opaque, require `producerVersion`, keep failure codes open under their syntax rule, and do not select B1/B2/B3 here. | This provides traceability without selecting or coupling to a research producer. | `APPROVE / EXCEPTION: ____________________` |

## Remaining shared decisions

| ID | Existing recommended choice | One-sentence rationale | Response — initially `PENDING` |
|---|---|---|---|
| S-01 | Keep immutable `originalAutomaticValue` and canonical `presentationValue`; permit only the role-specific equality and lexical money-normalization rules already defined. | Android needs deterministic values without losing or silently correcting backend output. | `APPROVE / EXCEPTION: ____________________` |
| S-02 | Require `MYR`; money is nonnegative plain decimal with exactly two fractional digits; date is Gregorian-valid ISO; quantity is positive plain decimal with maximum scale three; reject signs, exponents, unsupported locale/grouping forms, NaN/infinity, and rounding. | Freezing one grammar prevents Kotlin/Python divergence and preserves weighted quantities. | `APPROVE / EXCEPTION: ____________________` |
| S-03 | Make JSON array order normative, use exact receipt/item role order, retain source row order, and add no redundant row index. | This follows Contract V0 tuple order and prevents array/index contradictions. | `APPROVE / EXCEPTION: ____________________` |
| S-04 | Use case-sensitive opaque IDs matching `[A-Za-z0-9][A-Za-z0-9._-]*`; enforce uniqueness, validate request/image context, and forbid paths, URIs, whitespace, content, participant IDs, and evaluation IDs in references. | This provides safe correlation without leaking machine-local or research identities. | `APPROVE / EXCEPTION: ____________________` |
| S-05 | Permit `LOCAL_IMAGE` and fixture-only `SYNTHETIC_FIXTURE`; make SHA-256 null or 64 lowercase hex, while leaving production digest population deferred. | This separates fixture/live policy and deterministic syntax from the later privacy decision. | `APPROVE / EXCEPTION: ____________________` |
| S-07 | Reject unknown members at every wrapper/envelope object level and reject duplicate keys; additive members require a new schema version. | Fail-closed V1 produces identical Kotlin/Python acceptance behavior. | `APPROVE / EXCEPTION: ____________________` |
| S-08 | Preserve `ReceiptOutput.extraction_status` exactly and validate enum membership only; do not recompute B1/B2 completeness in presentation validators. | Contract V0 does not enforce producer-specific derivation, so recomputation risks cross-runtime drift. | `APPROVE / EXCEPTION: ____________________` |
| S-09 | Enforce the defined missing/unresolved/extracted state, token, and finite-confidence rules; Python validates IDs against full evidence, while V1 reasons remain privacy-safe opaque free text and reason codes are deferred. | This separates cross-runtime reference integrity from backend-only evidence authenticity. | `APPROVE / EXCEPTION: ____________________` |
| S-10 | Omit external unit-price reference evidence from V1; its absence says nothing about availability or correctness, and any later addition requires a typed extension/version. | Contract V0 keeps reference evidence separate and does not bind it to an item row here. | `APPROVE / EXCEPTION: ____________________` |
| S-11 | Keep `producerId` opaque and case-sensitive and require nonblank `producerVersion`; do not encode B1/B2/B3 as a closed enum. | This enables traceability without selecting a live extractor in this design milestone. | `APPROVE / EXCEPTION: ____________________` |

## Contract V0 and evidence boundary confirmation

Approval of the rows above confirms only a presentation projection. It does not
change Contract V0, B1/B2/B3 behavior, proposed-method or evaluation schemas,
and it does not permit projected token IDs to be described as evidence
authenticity unless the backend has validated them against full immutable source
evidence before emission.

## Ready-to-copy Leng response

> I, Leng Wei Heng, independently reviewed approval candidate
> `M3D-1-APPROVAL-CANDIDATE-2026-11-04` and its consolidated register. I record
> my responses to L-01 through L-07 and remaining shared decisions S-01 through
> S-05 and S-07 through S-11 as marked in this questionnaire. I acknowledge the
> previously recorded S-06 shared-owner design agreement without reopening it.
> My explicit exceptions, if any, are: `[none or list exact IDs and required
> wording]`. This response does not authorize Kotlin/Python implementation, OCR
> orchestration, runtime integration, persistence, scoring, calibration,
> evaluation, backend activation, or real-receipt processing.

**Leng name/date:** `________________________________________`

## Classification

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_FULL_CONTRACT_APPROVAL_PENDING`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
