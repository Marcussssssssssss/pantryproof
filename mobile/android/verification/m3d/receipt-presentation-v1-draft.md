# Receipt Presentation Contract V1 — Draft Proposal

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

**Project:** PantryProof FYP2  
**Owners:** Tai Yong Xin (Android) and Leng Wei Heng (backend)  
**Milestone:** TAI-LENG-M3D-0  
**Date:** 2026-11-04  
**Research status:** `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

## 1. Status and scope

This document proposes a language-neutral JSON projection called
`receipt-presentation-v1`. It is a design artifact for shared review, not an
approved runtime interface.

The proposal carries a pre-review automatic receipt result from a future local
processor to the Kotlin Android presentation layer. It preserves incomplete
fields and evidence identities without serializing Python objects, Android
objects, OCR text/geometry, evaluation data, or inventory operations.

This milestone does **not** authorize or implement:

- OCR execution or source-gate orchestration;
- selection or alteration of B1, B2, B3, or the proposed method;
- correction, scoring, confidence calibration, or threshold logic;
- Android parsing, processing gateways, networking, or backend activation;
- human-review writeback, persistence, or inventory synchronization; or
- real-receipt or held-out evaluation.

Every accompanying JSON file is fictional and wrapped with the marker
`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`.

## 2. Repository evidence and compatibility preflight

### 2.1 Git foundation

| Check | Observed value |
|---|---|
| Repository | `D:/PantryProof` |
| Remote | `origin https://github.com/Marcussssssssssss/pantryproof` |
| Branch | `feature/tai-android-ui` |
| HEAD | `f218e0ed5f741c0b113a46d0f23f99c27dc45cb7` |
| Expected HEAD | Exact match |
| Staged changes before M3D-0 | None |
| Tracked working-tree changes before M3D-0 | None |
| Existing untracked paths | `.agents/`, `docs/ui_ux_design_direction_v0.md`, `mobile/android/verification/`, `skills-lock.json` |
| Secondary worktree | `D:/PantryProof-android-ui`, detached at `63317df1fbed042cb035db54b1ac7a604f7f3555` |

The secondary worktree was not opened or modified. No Git staging, commit,
push, merge, rebase, reset, stash, clean, or worktree operation was performed.

### 2.2 Contract V0 evidence

The proposal is a **presentation projection**, not a lossless serialization or
replacement of Contract V0:

- `pipeline/contracts.py:15` fixes `CONTRACT_VERSION = "0"`.
- `ReceiptFieldName` at line 30 defines the seven field roles.
- `FieldStatus` at line 40 defines `EXTRACTED`, `MISSING`, and `UNRESOLVED`.
- `ReceiptExtractionStatus` at line 46 is structural completeness, not accuracy.
- `StructuredField` at line 197 defines value/status/reason, identity, source
  token, and optional native-confidence invariants.
- `ReceiptItemRow` at line 247 defines four item fields and row identity.
- `ReceiptOutput` at line 289 binds receipt output to sufficient source evidence,
  an extractor version, and `PRE_REVIEW_AUTOMATIC` output stage.
- `ExternalPriceReference` at line 411 is distinct from extracted unit-price
  truth.

`pipeline/ocr_adapter.py::adapt_paddleocr_result` and
`attach_gate_result` (lines 52 and 133) stop at evidence construction. B1 and B2
require already-gated `ReceiptSourceEvidence`; B3 requires B2 output. There is no
current image-to-product-response orchestrator or Contract V0 JSON serializer.

Current producer identifiers exist, but this draft does not select one:

- B1: `B1-deterministic-v1` (`pipeline/baseline_b1.py:31`)
- B2: `B2-layout-graph-v0` (`pipeline/layout_b2.py:33`)
- B3: `B3-generic-rules-v0` (`pipeline/baseline_b3.py:35`)

### 2.3 Android evidence

- `ReceiptModels.kt:6-18` represents only a completed typed receipt: required
  strings/date/totals, integer quantity, and nullable unit price.
- `ReceiptValidator.kt:94-155` validates ISO dates, positive integer quantities,
  and non-negative money with at most two decimal places.
- `ReceiptPresentationSource.kt:7-9` currently exposes only synthetic receipt and
  inventory data and explicitly avoids coupling to Python evaluation objects.
- The app targets API 26 (`app/build.gradle.kts:14`) and has no production JSON,
  OCR, HTTP, database, or Python dependency.
- M3C concluded that automatic incomplete data must remain separate from the
  existing completed `Receipt` model and editable draft.

The proposed JSON uses only UTF-8 objects, arrays, strings, booleans, finite
numbers, and null. It does not require Android, Kotlin, or Python type tags and is
feasible to decode on API 26 after a parser is separately approved.

## 3. Fixture wrapper versus runtime envelope

The draft JSON files are test examples, so each file has a non-runtime wrapper:

```json
{
  "fixtureStatus": "DRAFT_NOT_APPROVED — SYNTHETIC_ONLY",
  "scenario": "complete-extracted-receipt",
  "expectedResult": "ACCEPT",
  "envelope": {}
}
```

`fixtureStatus`, `scenario`, and `expectedResult` are fixture metadata. They are
not proposed runtime-envelope members. `expectedResult` is one of:

- `ACCEPT`
- `REJECT_UNSUPPORTED_SCHEMA_VERSION`
- `REJECT_CONTRADICTORY_FIELD_STATE`

The object nested at `envelope` is the proposed runtime shape.

## 4. Proposed envelope

### 4.1 Structural outline

```json
{
  "schemaName": "receipt-presentation",
  "schemaVersion": "1",
  "sourceContractVersion": "0",
  "requestId": "request-synthetic-001",
  "imageId": "image-synthetic-001",
  "source": {
    "type": "SYNTHETIC_FIXTURE",
    "provenance": {
      "sourceSystem": "M3D_SYNTHETIC_FIXTURE",
      "sourceReference": "source-synthetic-001",
      "contentSha256": null
    }
  },
  "outcome": {
    "status": "RESULT_AVAILABLE",
    "failure": null
  },
  "sourceEvidence": {
    "sourceProcessingStatus": "OCR_COMPLETED",
    "tokenIds": ["token-synthetic-001"]
  },
  "sourceGate": {
    "gateResultId": "gate-synthetic-001",
    "decision": "SUFFICIENT",
    "reasons": []
  },
  "automaticExtraction": {
    "stage": "PRE_REVIEW_AUTOMATIC",
    "extractionStatus": "EXTRACTED",
    "producer": {
      "producerId": "SYNTHETIC_FIXTURE_PRODUCER",
      "producerVersion": "draft-1"
    }
  },
  "receipt": {
    "receiptId": "receipt-synthetic-001",
    "receiptFields": [],
    "itemRows": []
  }
}
```

This is a terminal presentation envelope. `PROCESSING_IN_PROGRESS` remains an
Android controller/UI state rather than a serialized backend result in V1.
Likewise, “no image selected” precedes request/image identity creation and is not
a cross-runtime envelope.

### 4.2 Top-level members

| Member | Type | Required | Definition |
|---|---|---:|---|
| `schemaName` | string | Yes | Exact value `receipt-presentation`. |
| `schemaVersion` | string | Yes | Exact supported value `1`. Any other value is rejected before mapping. |
| `sourceContractVersion` | string | Yes | Contract V0 projection uses exact value `0`; this does not change Contract V0. |
| `requestId` | opaque string | Yes | Android-created processing-attempt correlation ID. It is not an evaluation ID. |
| `imageId` | opaque string | Yes | Shared opaque image identity. It is not an Android URI or path. |
| `source` | object | Yes | Source classification and privacy-safe provenance. |
| `outcome` | object | Yes | Terminal presentation outcome and optional failure diagnostic. |
| `sourceEvidence` | object or null | Yes | Contract evidence summary with token-ID registry; never OCR text or geometry. |
| `sourceGate` | object or null | Yes | Recorded gate result where one exists. Null means no gate result is represented; it does not add a Contract V0 decision. |
| `automaticExtraction` | object or null | Yes | Producer and extraction metadata for an available result. |
| `receipt` | object or null | Yes | Automatic receipt projection for an available result. |

IDs and opaque references are proposed as nonblank ASCII tokens matching
`[A-Za-z0-9][A-Za-z0-9._-]*`. This deliberately excludes slashes, backslashes,
URI schemes, drive prefixes, and whitespace. The exact grammar is a shared
approval point because Contract V0 currently requires only nonblank text.

### 4.3 Source and provenance

```json
{
  "type": "SYNTHETIC_FIXTURE",
  "provenance": {
    "sourceSystem": "M3D_SYNTHETIC_FIXTURE",
    "sourceReference": "source-synthetic-001",
    "contentSha256": null
  }
}
```

Proposed `source.type` values:

- `LOCAL_IMAGE`: a future real local import/capture processing request.
- `SYNTHETIC_FIXTURE`: reserved for contract tests and forbidden in a live
  local-image processing flow.

The existing Android synthetic demo remains outside this envelope and must not
be represented as extracted local-image content.

`sourceSystem` and `sourceReference` project Contract V0 `SourceProvenance` but
must be opaque. They must not contain an Android URI, local filesystem path,
participant identifier, evaluation/reference identity, or receipt text.

`contentSha256` is null or a 64-character lowercase hexadecimal string. Whether
a digest may cross the production boundary is still a shared privacy decision;
all fixtures use null.

### 4.4 Outcome and failure

`outcome.status` is a presentation-layer enum:

- `RESULT_AVAILABLE`
- `PROCESSING_UNAVAILABLE`
- `PROCESSING_FAILED`

For `RESULT_AVAILABLE`, `failure` is null and source evidence, sufficient gate,
automatic extraction, and receipt are required.

For `PROCESSING_UNAVAILABLE` or `PROCESSING_FAILED`, `receipt` and
`automaticExtraction` are null and `failure` is required:

```json
{
  "stage": "AVAILABILITY",
  "code": "PROCESSOR_NOT_AVAILABLE",
  "retryable": false
}
```

Proposed `stage` values are `AVAILABILITY`, `OCR`, `SOURCE_GATE`, `EXTRACTION`,
and `PRESENTATION_ADAPTER`. The stable `code` is a nonblank uppercase token,
not a localized message. Android maps it to safe user-facing text and must use a
generic fallback for an unrecognized code. This taxonomy is presentation-layer
work pending joint approval; it is not defined by Contract V0.

### 4.5 Source evidence and source gate

`sourceEvidence.sourceProcessingStatus` preserves the exact Contract V0 enum:

- `RECEIVED`
- `OCR_COMPLETED`
- `OCR_PARTIAL`
- `OCR_FAILED`

`tokenIds` is an ordered, duplicate-free registry of opaque token identities.
It intentionally omits OCR text, confidence, polygons, and image bytes. Every
field source-token reference must resolve to this registry.

This JSON object is a minimal presentation summary, not a serialization of the
full Contract V0 `ReceiptSourceEvidence`. On a failure before gating it may
summarize the adapter's source-processing status while `sourceGate` remains null;
an available receipt still requires the complete sufficient-gate relationship
enforced by Contract V0.

`sourceGate`, when non-null, contains:

| Member | Rule |
|---|---|
| `gateResultId` | Required nonblank opaque identity. |
| `decision` | Exact Contract V0 enum `SUFFICIENT` or `INSUFFICIENT`. |
| `reasons` | Ordered, unique nonblank strings; at least one for `INSUFFICIENT`. |

Reasons must be privacy-safe and must not reproduce OCR text, image paths,
Android URIs, participant identities, or evaluation references.

Contract V0 forbids `ReceiptOutput` from insufficient source evidence. Therefore
`RESULT_AVAILABLE` requires a non-null gate with `SUFFICIENT`. A null gate means
“not represented/not reached” at this presentation boundary; it does not invent
`NOT_EVALUATED` as a Contract V0 decision.

### 4.6 Automatic extraction metadata

```json
{
  "stage": "PRE_REVIEW_AUTOMATIC",
  "extractionStatus": "PARTIAL",
  "producer": {
    "producerId": "SYNTHETIC_FIXTURE_PRODUCER",
    "producerVersion": "draft-1"
  }
}
```

- `stage` is exactly `PRE_REVIEW_AUTOMATIC` in V1.
- `extractionStatus` preserves Contract V0 `EXTRACTED`, `PARTIAL`, or `FAILED`.
- `producerId` is an opaque identifier; it is not a closed B1/B2/B3 enum.
- `producerVersion` projects `ReceiptOutput.extractor_version` or an approved
  adapter equivalent.

The schema does not select a production producer. It also does not independently
recompute extraction status from fields in this draft because Contract V0's
constructor does not enforce that derivation. Whether a presentation adapter
must reproduce B1/B2 completeness logic is a shared decision.

## 5. Receipt and field structures

### 5.1 Receipt

```json
{
  "receiptId": "receipt-synthetic-001",
  "receiptFields": [],
  "itemRows": []
}
```

`receiptFields` is an ordered array containing exactly one field of each role in
this exact order:

1. `STORE_NAME`
2. `PURCHASE_DATE`
3. `RECEIPT_TOTAL`

`itemRows` is an order-significant JSON array. Array order is the receipt row
order. V1 does not add a redundant row index; this avoids contradictory index
and array order. Each row is:

```json
{
  "rowId": "receipt-synthetic-001-row-001",
  "fields": []
}
```

Every row contains exactly one field of each role in this exact order:

1. `ITEM_DESCRIPTION`
2. `QUANTITY`
3. `UNIT_PRICE`
4. `LINE_TOTAL`

Receipt identity and row identity are supplied by containment. The projection
does not duplicate Contract V0 `receipt_id` and `item_row_id` inside every field.
The backend adapter must validate those relationships before projection.

Zero rows remain structurally possible because Contract V0 does not require a
minimum row count. UI handling of that condition is separate from transport
validity.

### 5.2 Field shape

```json
{
  "fieldId": "receipt-synthetic-001-store-name",
  "role": "STORE_NAME",
  "status": "EXTRACTED",
  "originalAutomaticValue": "Kedai Runcit Harmoni",
  "presentationValue": "Kedai Runcit Harmoni",
  "absenceReason": null,
  "sourceTokenIds": ["token-synthetic-store"],
  "nativeConfidence": null
}
```

| Member | Meaning |
|---|---|
| `fieldId` | Stable, nonblank, receipt-wide unique automatic field identity. |
| `role` | One of the seven exact Contract V0 field-role strings. |
| `status` | Exact Contract V0 `EXTRACTED`, `MISSING`, or `UNRESOLVED`. |
| `originalAutomaticValue` | Exact `StructuredField.value` emitted by the selected automatic producer; immutable through manual review. |
| `presentationValue` | Canonical language-neutral value suitable for strict cross-runtime parsing. It is formatting normalization, not a correctness claim. |
| `absenceReason` | Nonblank producer reason for `MISSING`/`UNRESOLVED`; null for `EXTRACTED`. Not user-facing text by default. |
| `sourceTokenIds` | Ordered unique references into `sourceEvidence.tokenIds`. |
| `nativeConfidence` | Null or finite JSON number copied from native evidence. It is not calibrated and has no implied 0-1 range. |

The dual value is necessary because B1/B2 currently preserve recognized money
text that may include `RM`, `MYR`, `$`, or grouping separators, while the
presentation contract requires plain decimal strings. Both values prevent
format normalization from hiding or overwriting the original automatic output.

Field-state rules preserve Contract V0:

| Status | Value rules | Reason | Confidence | Token references |
|---|---|---|---|---|
| `EXTRACTED` | Both values non-null and nonblank | Must be null | Null or finite number | At least one unique resolvable token ID |
| `MISSING` | Both values null | Required nonblank | Must be null | Empty or resolvable IDs; Contract V0 does not require empty |
| `UNRESOLVED` | Both values null | Required nonblank | Must be null | Empty or resolvable IDs; may retain ambiguous evidence |

Every item row must contain at least one OCR-backed `EXTRACTED` field, preserving
`ReceiptItemRow`'s Contract V0 invariant.

## 6. Seven-field representations

| Role | `originalAutomaticValue` | `presentationValue` draft rule | Missing/unresolved handling | Android mapping |
|---|---|---|---|---|
| `STORE_NAME` | Exact extracted Unicode text | Exact same nonblank text; no normalization in V1 | Both values null plus reason | Populate review string only; do not construct typed receipt until valid |
| `PURCHASE_DATE` | Exact producer value | Gregorian-valid ISO `YYYY-MM-DD` | Both values null plus reason | Parse to `LocalDate` only after validation |
| `ITEM_DESCRIPTION` | Exact extracted Unicode text | Exact same nonblank text; no correction/normalization | Both values null plus reason | Blank incomplete review field while retaining field/row IDs |
| `QUANTITY` | Exact producer numeric text | Positive plain decimal string, integer or weighted; no sign, exponent, separator, or rounding | Both values null plus reason | Keep as string/decimal in automatic model; do not coerce to current `Int` inventory |
| `UNIT_PRICE` | Exact producer money text | Non-negative plain decimal string with exactly two fractional digits | Missing remains valid/optional for Android confirmation; unresolved remains explicitly unresolved | Map extracted value to `BigDecimal`; blank optional draft for missing |
| `LINE_TOTAL` | Exact producer money text | Non-negative plain decimal string with exactly two fractional digits | Both values null plus reason | Map only after strict decimal validation |
| `RECEIPT_TOTAL` | Exact producer money text | Non-negative plain decimal string with exactly two fractional digits | Both values null plus reason | Map only after strict decimal validation |

Proposed canonical regular languages, pending shared approval:

- money: `^(0|[1-9][0-9]*)\.[0-9]{2}$`
- quantity: `^(0|[1-9][0-9]*)(\.[0-9]+)?$`, plus numeric value greater than zero
- date: lexical `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` plus a real Gregorian
  calendar validity check

No numeric value may use a sign, exponent, currency prefix, grouping separator,
leading zero (except `0`), NaN, infinity, or binary floating-point transport.
Maximum quantity scale is unresolved and recorded for joint review.

### 6.1 Unit-price evidence separation

V1 contains only the automatically extracted `UNIT_PRICE` field. It deliberately
does not serialize `ExternalPriceReference` because Contract V0 does not bind
that record to an item row in this projection.

Therefore:

- `UNIT_PRICE/MISSING` means the automatic receipt output did not supply an
  extracted unit price;
- it does **not** mean retailer reference evidence was unavailable;
- external evidence must never fill `presentationValue` or imply correctness;
  and
- adding external reference evidence requires a distinct, jointly approved
  section or later schema version.

### 6.2 Manual-review survival

The automatic envelope is immutable. Android may derive a separate editable
draft:

- extracted `presentationValue` becomes the initial draft value;
- missing/unresolved becomes a blank draft plus retained status/reason metadata;
- `receiptId`, `rowId`, `fieldId`, original values, statuses, token IDs, producer,
  source, and gate stay unchanged; and
- user edits never overwrite the automatic envelope.

The current Android `Receipt` remains a completed reviewed presentation model.
Decimal receipt quantities cannot be silently rounded or copied into the
existing integer inventory. Review writeback is outside V1.

## 7. Strict validation and rejection behavior

Validation is fail-closed for defined V1 semantics. A consumer rejects the
entire envelope, rather than partially displaying it as extracted, for any of
the following.

### 7.1 Version and JSON structure

- missing or incorrect `schemaName`;
- missing or unsupported `schemaVersion`;
- unsupported `sourceContractVersion`;
- duplicate JSON object member names;
- missing required members or wrong JSON types;
- unknown enum values; or
- unknown required field roles.

Whether otherwise unknown object members are rejected or ignored within schema
V1 is a pending shared versioning decision. No implementation may silently pick
a policy before approval.

### 7.2 Identity and ordering

- blank/malformed required IDs;
- caller-expected `requestId` or `imageId` mismatch;
- duplicate field IDs anywhere in one receipt;
- duplicate row IDs;
- duplicate source token IDs;
- duplicate token references inside a field;
- source-token reference absent from the token registry;
- missing, duplicate, unknown, or out-of-order receipt/item roles; or
- map/object-based or otherwise ambiguous item-row ordering.

JSON array order is normative. Consumers must not sort rows by display text,
field ID, or locale.

### 7.3 Values and field states

- invalid date or decimal grammar;
- money without exactly two fractional digits under the proposed rule;
- zero/negative quantity, exponent notation, grouping, currency in
  `presentationValue`, or silent numeric rounding;
- `EXTRACTED` with a null/blank value, absent token reference, or non-null reason;
- `MISSING`/`UNRESOLVED` with any value, native confidence, or no reason;
- text `presentationValue` differing from `originalAutomaticValue` in V1; or
- non-finite native confidence.

### 7.4 Cross-object state

- `RESULT_AVAILABLE` without source evidence, sufficient gate, extraction
  metadata, and receipt;
- result available with an `INSUFFICIENT` gate;
- available result carrying a failure diagnostic;
- unavailable/failed outcome carrying a receipt or extraction metadata;
- unavailable/failed outcome without a failure diagnostic;
- insufficient gate without at least one reason;
- item row with no OCR-backed extracted field; or
- live flow accepting `SYNTHETIC_FIXTURE` as a local-image result.

The draft does not independently reject an `extractionStatus` based solely on a
recalculation from field states until Tai and Leng decide whether that rule is
part of this projection.

## 8. Required fixture scenarios

| File | Expected result | Purpose |
|---|---|---|
| `01-complete-extracted-receipt.draft.json` | Accept | Complete fictional receipt with all seven roles and sufficient gate |
| `02-missing-optional-unit-price.draft.json` | Accept | Unit price absent without invented value; structural result partial |
| `03-missing-required-store-name.draft.json` | Accept | Required field retained as `MISSING` for manual correction |
| `04-unresolved-purchase-date.draft.json` | Accept | Ambiguous date with null values and retained token reference |
| `05-decimal-weighted-quantity.draft.json` | Accept | Quantity `0.750` retained without integer conversion |
| `06-processing-unavailable.draft.json` | Accept | No processor result, no gate, no receipt |
| `07-processing-failure.draft.json` | Accept | OCR failure diagnostic and no fabricated receipt |
| `08-unsupported-schema-version.draft.json` | Reject | Fail before payload mapping when schema version is unsupported |
| `09-malformed-status-value.draft.json` | Reject | `MISSING` field illegally contains values and lacks a reason |

All examples use fictional Malaysian grocery names and synthetic identities.
They contain no receipt image, participant data, reference/annotation identity,
ground truth, score, probability, or evaluation result.

## 9. Android/API 26 compatibility findings

- The JSON uses platform-neutral primitives and decimal strings, so API 26 does
  not require Java floating-point interpretation for money or quantity.
- Parser-library choice remains an Android implementation decision. The schema
  does not require Kotlin serialization annotations or sealed-class tags.
- Unsupported versions and enum/role violations must be rejected before mapping
  to Android UI models.
- `Uri` remains Android-local and is correlated only through opaque request and
  image IDs.
- Missing/unresolved automatic fields require a new immutable transport model;
  they cannot be forced into current `ReceiptModels.kt`.
- Existing `EditableReceipt` strings are suitable as a conceptual manual form,
  but they must be derived without destroying automatic status/provenance.
- Blank missing optional unit price remains nonblocking.
- Decimal quantity remains a receipt value. It does not alter the current
  integer, 0-99 temporary inventory model.
- A failed/unavailable local request must never display mock fields as extracted.
  The current synthetic demo path stays separate.

## 10. Contract V0 alignment and deliberate projection differences

| Topic | Alignment | Projection-only addition/omission |
|---|---|---|
| Versions | Carries source Contract V0 identity | Adds independent presentation schema name/version |
| Seven roles and field status | Exact enum strings | Fixes JSON field-array order |
| Values/reasons/confidence | Preserves original value, absence reason, nullable native confidence | Adds canonical `presentationValue`; no calibrated meaning |
| Receipt/row/field identity | Preserved | Parent containment removes redundant receipt/row IDs from each field |
| Token provenance | Preserves token identifiers and reference integrity | Omits OCR text, polygons, and token confidence for privacy/minimality |
| Gate | Preserves recorded ID, decision, reasons | Null means no gate represented; not a new V0 decision |
| Output | Preserves extraction status, stage, producer version | Adds producer ID and terminal outcome/failure presentation layer |
| External price | Kept semantically separate | Omitted from V1 rather than conflated with unit price |
| Review/persistence | No V0 behavior redefined | Entirely excluded |

This projection must not be advertised as a byte-for-byte or lossless
`ReceiptOutput` serialization.

## 11. Responsibility review

### 11.1 Tai review

Tai should verify:

- DTO and strict parser feasibility on API 26;
- immutable incomplete-field representation outside current `Receipt`;
- direct, provenance-preserving derivation of Manual Review strings;
- local-image and existing synthetic-demo isolation;
- optional missing unit price remaining nonblocking;
- decimal receipt quantity remaining separate from integer inventory; and
- safe user labels for field state, producer state, and failure codes.

### 11.2 Leng review

Leng should verify:

- every accepted fixture can be projected from structurally valid Contract V0
  concepts without changing B1/B2/B3 semantics;
- exact original values and deterministic presentation values can both be emitted;
- receipt, image, gate, row, field, and token IDs are stable for one result;
- token-ID registry projection preserves reference integrity;
- producer/stage and source-gate metadata are available at the future boundary;
- no raw path/URI or evaluation identity is serialized; and
- future failure mapping can use the proposed outer taxonomy without modifying
  Contract V0 decisions.

### 11.3 Joint review

The concise approval points are maintained in
`shared-decision-register.md`. OCR orchestration, production producer selection,
runtime packaging, persistence, correction/scoring, and evaluation remain later
decisions and are not requests for approval in M3D-0.

## 12. Exact next step after joint approval

The smallest implementation milestone is **synthetic conformance only**:

1. Freeze the approved schema text and accepted/rejected fixture bytes under a
   jointly selected version.
2. Leng implements a Python projection/validator only for handcrafted synthetic
   Contract V0 records; it does not run OCR, gating, extraction, or evaluation.
3. Tai implements API-26-compatible Kotlin DTO decoding/validation against the
   same fixture bytes; production navigation and picker behavior stay unchanged.
4. Both sides prove identical accept/reject outcomes and value/identity mappings.
5. Preserve the existing Android 15 unit and 13 instrumentation scenarios and
   rerun API 26/API 36 regression after implementation.

No processing gateway or real backend activation should begin until that
separately authorized milestone passes.

## Classification

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

`CONTRACT_DESIGN_PENDING_SHARED_APPROVAL`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
