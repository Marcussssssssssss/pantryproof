# Receipt Presentation V1 — Contract Closure Proposal

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

**Package ID:** `M3D-0R-PROPOSAL-2026-11-04`  
**Approval candidate:** `M3D-1-APPROVAL-CANDIDATE-2026-11-04`  
**Owners for independent review:** Tai Yong Xin and Leng Wei Heng  
**Status:** `M3D_FULL_CONTRACT_APPROVAL_PENDING`  
**Recorded shared decision:** `S06_SHARED_OWNER_DESIGN_AGREED`  
**Research status:** `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

## 1. Purpose and authority

This document prepares the M3D design for independent owner review. S-06 is a
recorded shared-owner design agreement; every other S decision remains a
**recommendation**, not an approved decision. It does not authorize a
Kotlin/Python implementation, OCR, extraction orchestration, production
integration, persistence, scoring, calibration, evaluation, or use of real
receipt data.

The original M3D-0 contract draft and nine fixture bytes are preserved. The
decision register is updated only to record the completed S-06 agreement and
the still-pending remainder. Any approved successor fixture set must be created
as a new reviewed revision; original fixture bytes must not be silently
rewritten.

## 2. Git and source preservation

Preflight on 2026-11-04 found:

- repository `D:/PantryProof`;
- branch `feature/tai-android-ui`;
- HEAD `f218e0ed5f741c0b113a46d0f23f99c27dc45cb7`, matching the expected HEAD;
- no staged or tracked working-tree changes before M3D-0R;
- existing untracked `.agents/`, design documentation, Android verification
  artifacts, and `skills-lock.json` preserved; and
- detached `D:/PantryProof-android-ui` worktree at `63317df1...` untouched.

Source SHA-256 inventory after M3D-1 reconciliation:

| Source | SHA-256 |
|---|---|
| `receipt-presentation-v1-draft.md` | `1E56F3C82716E889E46DEEE898233C2C143FDD6122F715A1C8E32EADCCCB01E5` |
| `shared-decision-register.md` | `5C3284D54C604CC71293DDC4FD3EB87E2B8099A38DF4CA9A915403BB667DBB16` |
| `01-complete-extracted-receipt.draft.json` | `C76BB1EA58A73A81FA19243CE4D45ACB7DB136CED3460F727E0F8DEB36FEAF5D` |
| `02-missing-optional-unit-price.draft.json` | `5E237E8CDF221B04760D0352590F42A3FC6B6D74A06124787EA2BA42B887E438` |
| `03-missing-required-store-name.draft.json` | `9A1AC3E975E6EAE2C113F4258F5608F33062294B3439869B0AD2B0F9E5F533D8` |
| `04-unresolved-purchase-date.draft.json` | `292EE376D6895AF206E206F6429C0A26130573C9BDC571DEC5BD7D1D5299A067` |
| `05-decimal-weighted-quantity.draft.json` | `725C581AA4DAF6FF72055B11E6C348A8443ACE6B4C3A1E4919F3AE31168945A0` |
| `06-processing-unavailable.draft.json` | `C5F74B21D43E6362FC500CB394D0210B0C7C55F5DBDF6B4C0C02AB9622AE3EB2` |
| `07-processing-failure.draft.json` | `97B665B8BAF4F464372222DD4B60BABE48314C5A7E9E718704009DE6725CE82E` |
| `08-unsupported-schema-version.draft.json` | `6338E21A41AC681015CBD665CA7E3D5EA8C3BE1A80DD3532DDEBF2C82D082E77` |
| `09-malformed-status-value.draft.json` | `0E4BE41FE6A1C6DF4032874789FFC3ADA4848FD14BDF922206D0D9F6BA833096` |

## 3. Cross-runtime deterministic baseline

The following recommendations apply before S-01 through S-11. They are needed
so a Kotlin and Python validator cannot disagree due to parser defaults.

### 3.1 JSON bytes and structure

- Input is strict UTF-8 without a byte-order mark.
- Exactly one JSON root object is permitted.
- Comments, trailing commas, nonstandard `NaN`/`Infinity` tokens, malformed
  Unicode, and trailing non-whitespace bytes are rejected.
- Duplicate object-member names are rejected during lexical parsing, before an
  ordinary map/object can overwrite them.
- Object-member order is semantically irrelevant. Array order is normative.
- Member names and enum/ID values are case-sensitive.
- A required nullable member must be present with explicit JSON `null`; absent
  and null are not interchangeable.
- No string/number/boolean coercion is permitted.
- Unsupported `schemaName`, `schemaVersion`, or `sourceContractVersion` is
  rejected before payload mapping.

### 3.2 Numeric and string interpretation

- Money and quantity are validated as strings using arbitrary-precision decimal
  parsing (`BigDecimal`/`Decimal`), never binary floating point.
- The validator does not recalculate receipt arithmetic, compare totals, or make
  a correctness claim.
- `nativeConfidence`, when non-null, is a JSON number that must be representable
  as finite IEEE-754 binary64 on both runtimes. It has no 0-1 restriction and no
  calibrated-probability meaning.
- “Nonblank” means the string contains at least one character other than exactly
  U+0009, U+000A, U+000D, or U+0020. No implicit Unicode normalization, trim,
  case-folding, or locale transform occurs.

### 3.3 Validation context

Envelope validation alone cannot detect a stale but internally well-formed
request/image result. The future validator API and mismatch fixtures therefore
receive non-runtime context:

```json
{
  "consumerContext": {
    "expectedRequestId": "request-expected-001",
    "expectedImageId": "image-expected-001",
    "mode": "FIXTURE"
  }
}
```

`consumerContext` belongs to the fixture wrapper/test harness, never the runtime
envelope. Existing fixtures without this member may default expected IDs to the
IDs inside their envelope; their bytes and expected results remain unchanged.

## 4. Shared S-01 through S-11 recommendations

### S-01 — Original and presentation values

**Recommended proposal**

Keep both `originalAutomaticValue` and `presentationValue`.

- Store name and item description: decoded strings must be exactly equal; no
  trim, case, whitespace, or Unicode normalization.
- Purchase date: both values must be the same valid ISO `YYYY-MM-DD`. Current
  B1/B2 already emit canonical extracted dates. Ambiguous/noncanonical dates are
  represented as `UNRESOLVED`, not normalized by this adapter.
- Quantity: both values must be the same canonical decimal string. No leading
  zero normalization or scale change is performed.
- Money: the only permitted difference is deterministic lexical normalization.
  The original may have no prefix or an ASCII-case-insensitive `RM`/`MYR`
  prefix, optional ASCII spaces after the prefix, and valid comma grouping. The
  canonical value removes that prefix/space/grouping only. `$` is rejected
  because Contract V0 does not establish that it means MYR. No rounding,
  arithmetic, or correction is allowed.

The proposed exact original-money grammar is:

```text
^(?:(?i:RM|MYR)[ ]*)?(?:(?:0|[1-9][0-9]*)|(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+))\.[0-9]{2}$
```

Canonicalization removes only the matched prefix plus its following ASCII
spaces and all matched grouping commas. The result must exactly equal
`presentationValue` and satisfy the canonical money grammar in S-02.

**Rationale**

This preserves the exact Contract V0 output while making Android decimal parsing
deterministic. It prevents `presentationValue` from becoming an untraceable
automatic correction.

**Required successor-fixture action**

- Keep original fixture 01 unchanged.
- In its approved successor copy, change purchase-date
  `originalAutomaticValue` from `15/10/2026` to `2026-10-15`; expected result
  remains `ACCEPT`.
- Add accepted money-normalization and rejected value-divergence fixtures.

**Conformance status:** `BLOCKING_PROPOSAL`

### S-02 — Money, currency, date, and quantity grammar

**Recommended proposal**

- Add required `receipt.currencyCode` with exact V1 value `MYR` for every
  available receipt. This makes Android's RM formatting explicit rather than
  inferred from a currencyless number.
- `UNIT_PRICE`, `LINE_TOTAL`, and `RECEIPT_TOTAL` presentation values use
  `^(0|[1-9][0-9]*)\.[0-9]{2}$` and are non-negative. The rule includes unit
  price: one or three fractional digits are rejected, never rounded.
- `0.00` is valid money. Arithmetic relationships are not validated.
- Quantity uses `^(0|[1-9][0-9]*)(\.[0-9]{1,3})?$`, parsed value must be greater
  than zero, trailing zeros are preserved, and maximum scale is three.
- Date uses `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` and must be Gregorian-valid.
- Signs, exponent notation, locale decimal commas, grouping in canonical values,
  currency symbols in canonical values, NaN/infinity, and rounding are rejected.

**Rationale**

Current B1/B2 money recognition and Android validation use two fractional
digits. Three quantity decimals preserve the weighted `0.750` case while placing
the same explicit bound on both runtimes. `currencyCode` prevents a stripped
foreign symbol from being displayed as RM.

**Required successor-fixture action**

- Add `currencyCode: "MYR"` to successor copies of every available-receipt
  fixture (original fixtures 01-05 and 09).
- Add scale boundaries, invalid date, zero quantity, unsupported currency, and
  no-rounding fixtures.

**Conformance status:** `BLOCKING_PROPOSAL`

### S-03 — Ordering

**Recommended proposal**

JSON array order is normative. Receipt fields are exactly
`STORE_NAME, PURCHASE_DATE, RECEIPT_TOTAL`; item fields are exactly
`ITEM_DESCRIPTION, QUANTITY, UNIT_PRICE, LINE_TOTAL`; item-row array order is
source order. Do not add a redundant `rowIndex`.

**Rationale**

This follows Contract V0 tuple order and prevents array/index contradictions.

**Required fixture action**

Add a two-row non-lexical-order positive plus missing, duplicate, unknown, and
out-of-order role negatives.

**Conformance status:** `BLOCKING_PROPOSAL`

### S-04 — Identity, correlation, and privacy-safe references

**Recommended proposal**

- IDs and `sourceReference` match `[A-Za-z0-9][A-Za-z0-9._-]*` and compare
  case-sensitively.
- Field IDs are unique receipt-wide; row IDs and token-registry IDs are unique;
  source-token references are unique within a field.
- The validator compares `requestId` and `imageId` against caller-supplied
  expected context before display.
- `sourceReference` may not contain a URI, path separator, drive prefix,
  whitespace, receipt content, participant identity, or evaluation/reference ID.

**Rationale**

Internal JSON consistency cannot detect stale image attribution. Out-of-envelope
correlation and an opaque reference grammar close that boundary without exposing
Android URIs or machine paths.

**Required fixture action**

Add request mismatch, image mismatch, malformed ID, duplicate identity, and
unsafe URI/Windows-path references.

**Conformance status:** `BLOCKING_PROPOSAL`

### S-05 — Source type and content digest

**Recommended proposal**

- Valid source types are `LOCAL_IMAGE` and `SYNTHETIC_FIXTURE`.
- Contract validators accept `SYNTHETIC_FIXTURE`; application policy accepts it
  only when `consumerContext.mode` is `FIXTURE`.
- `contentSha256` is null or exactly 64 lowercase hexadecimal characters.
- Whether a production emitter populates a digest remains a separate privacy
  choice; V1 does not require it.

**Rationale**

This makes syntax deterministic while retaining local privacy control and
preventing fixture content from entering a live image path.

**Required fixture action**

Add valid digest, malformed/uppercase digest, local-image shape, and live-mode
synthetic-source fixtures.

**Conformance status:** source enum/digest grammar `BLOCKING_PROPOSAL`;
production digest population `DEFERRED`.

### S-06 — Outcome, failure, gate, and evidence state matrix

**Recorded shared-owner design**

Add a fourth terminal outcome,
`SOURCE_EVIDENCE_INSUFFICIENT`. Do not mislabel a recorded Contract V0
`INSUFFICIENT` decision as an operational failure.

| Outcome | Failure | Evidence | Gate | Extraction | Receipt |
|---|---|---|---|---|---|
| `RESULT_AVAILABLE` | null | Required genuine evidence; preserve any one of `RECEIVED`, `OCR_COMPLETED`, `OCR_PARTIAL`, or `OCR_FAILED` | Required actual source-bound `SUFFICIENT` | Required | Required |
| `PROCESSING_UNAVAILABLE` | Required; stage `AVAILABILITY` | null | null | null | null |
| `PROCESSING_FAILED` | Required | Required or null according to the technical-failure stage matrix below | Required or null according to the technical-failure stage matrix below | null | null |
| `SOURCE_EVIDENCE_INSUFFICIENT` | null | Required genuine evidence; preserve any one of `RECEIVED`, `OCR_COMPLETED`, `OCR_PARTIAL`, or `OCR_FAILED` | Required actual source-bound `INSUFFICIENT` with nonempty recorded reasons; response must be successfully constructed | null | null |

Leng's dated `APPROVE WITH EXCEPTIONS — S-06 SHARED RESOLUTION` response of
2026-11-04 records these two four-status outcome profiles and defers Case B
outside V1 JSON conformance. Tai approved the reconciled rules, and Leng
subsequently acknowledged and accepted that confirmation. S-06 is recorded as
`S06_SHARED_OWNER_DESIGN_AGREED`; complete M3D contract approval remains pending.

Leng's recorded backend conditions for technical-failure envelopes are:

| Failure stage | Evidence | Gate | Extraction / receipt |
|---|---|---|---|
| `OCR` | Null or genuine `OCR_FAILED` only | null | null / null |
| `SOURCE_GATE` | Required `OCR_COMPLETED` or `OCR_PARTIAL` | null; no durable gate result exists | null / null |
| `EXTRACTION` | Required `OCR_COMPLETED` or `OCR_PARTIAL` | Required recorded `SUFFICIENT` | null / null |
| `PRESENTATION_ADAPTER` | Required `OCR_COMPLETED` or `OCR_PARTIAL` | Required recorded `SUFFICIENT` | null / null |

Additional rules:

- `PROCESSING_FAILED` represents a technical failure, not insufficient evidence.
- An available receipt can preserve `extractionStatus: FAILED`; outer availability
  and Contract V0 structural extraction status are distinct. S-08 status
  preservation remains proposed and is not newly approved by these S-06
  subdecisions.
- `RESULT_AVAILABLE` accepts all four preserved Contract V0 evidence statuses
  only with a genuine structurally valid `ReceiptOutput`, actual evidence, an
  actual source-bound sufficient gate, required extraction metadata and receipt,
  consistent request/image identities, and preserved extraction status and
  original provenance. No status implies OCR success.
- `SOURCE_EVIDENCE_INSUFFICIENT` accepts all four preserved evidence statuses
  only with genuine evidence, an actual source-bound insufficient gate,
  nonempty recorded reasons, consistent identities, preserved status/token
  identities/provenance, and null technical failure, extraction, and receipt.
- The narrower evidence restrictions in the technical-failure stage matrix are
  unchanged and apply only to `PROCESSING_FAILED`.
- **Case A:** an actual `INSUFFICIENT` gate followed by successful presentation
  construction uses `SOURCE_EVIDENCE_INSUFFICIENT`.
- **Case B:** a backend presentation/projection exception after an actual
  `INSUFFICIENT` gate is
  `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`. It is not a successfully emitted
  insufficient response, `SOURCE_GATE` failure, current `PRESENTATION_ADAPTER`
  failure, unavailable outcome, or invented fifth outcome. No V1 JSON envelope,
  outcome, or stage is assigned; a later transport/error-handling design is
  required.
- `PRESENTATION_ADAPTER` means backend projection after a real Contract V0
  `ReceiptOutput`; Android decoding or semantic rejection remains local.
- A failure code is an open opaque token matching
  `[A-Z][A-Z0-9_]*`; Android uses a generic localized fallback for unknown codes.
- Failure stage is closed to `AVAILABILITY`, `OCR`, `SOURCE_GATE`, `EXTRACTION`,
  and `PRESENTATION_ADAPTER`.

**Rationale**

The matrix separates capability absence, technical failure, insufficient
evidence/fallback, and an available but structurally incomplete result.

**Required successor-fixture action**

Existing fixtures 06 and 07 remain unchanged. Add an accepted insufficient-gate
fixture for each preserved evidence status and the decided stage-specific
negative combinations. Fixtures 67 and 67a become proposed accepts only when
constructed from genuine structurally valid synthetic Contract V0 upstream
objects satisfying every available-result condition. Track Case B as a deferred
non-JSON lifecycle scenario without fabricating a response envelope or assigning
a V1 `ACCEPT`/`REJECT` expectation.

**Conformance status:** `S06_SHARED_OWNER_DESIGN_AGREED`; complete M3D contract
approval and any implementation authorization remain pending.

### S-07 — Unknown members and duplicate keys

**Recommended proposal**

Reject unknown members at every fixture-wrapper and envelope object level for
schema V1. Reject duplicate keys during lexical parsing. Additive members require
a new schema version. Failure codes remain open strings and are not “unknown
members.”

**Rationale**

Python and Kotlin libraries otherwise vary between last-value wins, first-value
wins, and error behavior. Fail-closed V1 makes acceptance identical.

**Required fixture action**

Add one raw duplicate-key fixture and unknown-member fixtures at representative
wrapper/envelope/field levels.

**Conformance status:** `BLOCKING_PROPOSAL`

### S-08 — Contract V0 extraction status

**Recommended proposal**

Preserve `ReceiptOutput.extraction_status` exactly and validate only enum
membership. Presentation validators do not recompute B1/B2 completeness.
Backend producer tests may separately assert producer-specific derivation before
projection.

**Rationale**

Recomputation would import producer behavior not enforced by the Contract V0
constructor and risks Kotlin/Python drift.

**Required fixture action**

Add an accepted available receipt with sufficient evidence and
`extractionStatus: FAILED`, missing top-level fields, and zero item rows. Add a
separate accepted fixture that distinguishes preservation from naïve UI
recomputation if both owners want an explicit discriminator.

**Conformance status:** `BLOCKING_PROPOSAL`

### S-09 — Missing/unresolved states, token integrity, and confidence

**Recommended proposal**

- `MISSING` and `UNRESOLVED` both require null values, null confidence, and a
  nonblank privacy-safe reason.
- Either state may contain zero or more unique, resolvable token references.
- `EXTRACTED` requires nonblank values, null reason, and at least one unique,
  resolvable token reference.
- The token registry contains unique IDs and all field references resolve to it.
- `nativeConfidence` follows the finite-binary64 rule in Section 3, with no
  calibrated range restriction.
- Reasons remain opaque free text in V1 and are never directly announced as
  trusted user-facing content. A controlled reason-code vocabulary is deferred.

**Trust boundary**

Kotlin can prove only projected internal reference integrity. It cannot prove
that an ID corresponds to actual OCR text/geometry because those are omitted.
Before emission, the Python projector must validate every ID against the full
immutable Contract V0 evidence. Neither side may label projected IDs as verified
OCR evidence.

**Required fixture action**

Add missing-with-token and unresolved-without-token positives; add dangling,
duplicate, blank-reason, missing-with-confidence, extracted-without-token, and
non-finite-confidence negatives. Add a finite confidence outside 0-1 positive to
prove no calibrated range was invented.

**Conformance status:** token/state rules `BLOCKING_PROPOSAL`; reason-code
vocabulary `DEFERRED`.

### S-10 — External unit-price reference evidence

**Recommended proposal**

Omit external price evidence from V1. Its absence says nothing about reference
availability and must not fill, validate, or imply correctness of extracted
`UNIT_PRICE`. Under S-07, an undeclared external-price member is rejected.

**Rationale**

Contract V0 keeps external reference evidence separate and does not bind it to
an item row in this presentation projection.

**Required fixture action**

No accepted fixture is needed. One unknown external-price member may exercise
the S-07 rejection rule.

**Conformance status:** V1 omission `BLOCKING_PROPOSAL`; future external-price
extension `DEFERRED_TO_NEW_VERSION`.

### S-11 — Producer identity

**Recommended proposal**

`producerId` is an opaque, case-sensitive protocol ID; `producerVersion` is a
required nonblank string. Neither is a closed B1/B2/B3 enum. Selecting the live
producer remains later work.

**Rationale**

This gives traceability without coupling consumer releases to a research
producer or selecting one in a design milestone.

**Required fixture action**

Existing synthetic producer identity demonstrates open IDs. Add missing/blank
producer-version rejection.

**Conformance status:** field shape `BLOCKING_PROPOSAL`; actual producer
selection `DEFERRED`.

## 5. Blocking versus deferred closure

S-06 is already `S06_SHARED_OWNER_DESIGN_AGREED` and is not reopened by the
remaining review.

### Must be jointly recorded before synthetic validators

- S-01 dual-value relationships and lexical normalization.
- S-02 currency, money/date/quantity grammar and quantity maximum scale.
- S-03 array/role/row ordering.
- S-04 identity grammar and caller correlation.
- S-05 source enum, test/live rule, and digest syntax.
- S-07 JSON/unknown-member/duplicate-key behavior.
- S-08 extraction-status preservation without recomputation.
- S-09 field-state, token-reference, confidence, and nonblank rules.
- S-10 explicit V1 omission of external price evidence.
- S-11 producer metadata shape.
- Section 3 strict JSON and primitive interpretation baseline.

### May be deferred without acceptance ambiguity

- Kotlin or Python parser-library selection.
- Canonical object-key ordering or byte-for-byte serializer output; semantic
  object order is irrelevant.
- Whether production populates `contentSha256`.
- Controlled/versioned absence-reason codes.
- Exhaustive failure-code catalogue; codes are open and have a generic UI path.
- Actual B1/B2/B3 producer selection.
- External-price schema extension.
- OCR/source-gate orchestration and runtime packaging.
- Manual-review writeback, persistence, inventory conversion, scoring,
  calibration, and evaluation.

## 6. Required review outcome

Tai and Leng should independently record their dispositions using the exact
M3D-1 questionnaires. Approval is valid only when it:

1. names approval candidate `M3D-1-APPROVAL-CANDIDATE-2026-11-04`;
2. states the disposition for T-01 through T-07 or L-01 through L-07;
3. states agreement or explicit exceptions for S-01 through S-05 and S-07
   through S-11, while acknowledging the recorded S-06 agreement without
   reopening it;
4. limits authority to a future separately scoped synthetic-conformance
   implementation; and
5. repeats that real backend activation remains unauthorized.

No silence, inferred consent, conversational summary, or file presence counts as
approval.

## 7. Smallest step after joint approval

After both owners record the required statements, the smallest separately
authorized implementation milestone should:

1. create a frozen successor copy of the nine baseline fixtures with only the
   approved updates;
2. add the blocking proposed fixtures listed in
   `fixture-expansion-proposal.md`;
3. implement one standalone Python semantic projector/validator over handcrafted
   synthetic Contract V0 records and one standalone API-26-compatible Kotlin
   decoder/validator over the same bytes;
4. compare accept/reject code, every retained identity, and every original and
   presentation value across both runtimes; and
5. leave `MainActivity`, production navigation, OCR, source-gate execution,
   backend activation, persistence, inventory, scoring, and evaluation untouched.

That implementation still requires separate authorization; this review package
does not grant it.

## Classification

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_FULL_CONTRACT_APPROVAL_PENDING`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
