# PantryProof — Android–Python Review Contract Specification (`receipt-review` v1)

**Status** `CONSOLIDATED_REVISION_FOR_JOINT_RATIFICATION`. Implementation requires joint ratification by Tai Yong Xin and Leng Wei Heng.  
**Scope:** Shared wire, schema, semantic, validation, and review-interaction contract extending Presentation V1 (`receipt-presentation` v1) without modifying V1.  
**Compatibility basis** The frozen Presentation V1 conformance implementations and fixtures define the embedded payload. `docs/proposed_receipt_correction_v1.md` describes the operational producer. This proposal leaves Contract V0 and Presentation V1 intact.

---

## 1. Purpose, Authority, and Scope

This specification defines the complete shared boundary between Leng's Python backend and Tai's Kotlin Android application for full seven-field receipt review under the **Price-Verified Self-Correction Pipeline**.

It operationalizes:

1. Tai's approved integration direction and consolidated review under `PANTRYPROOF_TAI_SHARED_REVIEW_CONTRACT_AND_PROTOTYPE_RUNTIME_REVIEW_01`, sections A–K. This revision supplies the exact shared choices for joint ratification.
2. The research obligations of the PantryProof methodology (Chapters 3–4 of `RSW_LengWeiHeng_FullText(Moderated).pdf` and supervisor guidelines), specifically:
   - strict separation of original OCR evidence, initial B2 `c0` extraction, development recommendations, policy-verified automatic decisions, unverified drafts, user edits, and final confirmed inventory records;
   - strict separation of primary receipt `ITEM_DESCRIPTION` from downstream pantry-normalised semantic identity;
   - preservation of null calibrated probabilities when unavailable (never misrepresenting raw model scores, OCR confidences, or evidence counts as calibrated probabilities); and
   - non-authoritative price plausibility (`PRICE_SUPPORTED`, `PRICE_CONFLICT`, `PRICE_UNAVAILABLE`, `PRICE_INCONCLUSIVE`) that cannot independently establish product identity or authorize replacement.

All examples and fixtures referenced by this document are synthetic contract examples only, not genuine OCR outputs or empirical research findings.

---

## 2. Versioning and Compatibility Mechanism

### 2.1 Compatibility Design Choice

Presentation V1 (`schemaName: "receipt-presentation"`, `schemaVersion: "1"`) enforces closed JSON object member sets (`_TOP_MEMBERS`, `_FIELD_MEMBERS`, `_RECEIPT_MEMBERS`, etc.) and rejects any unknown member with `REJECT_UNKNOWN_MEMBER`. Accordingly, **zero new members are added to Presentation V1**.

Instead, the contract uses a single **composition wrapper schema**:

- **Response schema name:** `"receipt-review"`
- **Response schema version:** `"1"`
- **Embedded presentation payload:** `"presentation"` contains an unmodified, strictly valid `receipt-presentation` v1 envelope (`schemaName: "receipt-presentation"`, `schemaVersion: "1"`, `sourceContractVersion: "0"`).
- **Review extension payload:** `"review"` contains the versioned seven-field review extension (or `null` when processing never began, i.e., `PROCESSING_UNAVAILABLE`).

This single shared representation allows both Python (`pipeline.presentation_v1.conformance.validate_presentation_v1_object`) and Android (`ReceiptPresentationV1Validator`) to validate `"presentation"` with zero modification to the frozen Presentation V1 rules, while isolating review decoding and validation under `"receipt-review"` v1.

### 2.2 Request-Side Version Selection

Version selection is controlled by one explicit HTTP request header on `POST /v1/receipts/process`:

| Header | Value | Behaviour |
| --- | --- | --- |
| `X-Response-Schema` | *(omitted)* | **Default compatibility mode.** Backend emits strict Presentation V1 (`schemaName: "receipt-presentation"`, `schemaVersion: "1"`). Existing V1 clients require no request change. |
| `X-Response-Schema` | `receipt-presentation-v1` | Explicit strict Presentation V1 selection. Same output as omitted header. |
| `X-Response-Schema` | `receipt-review-v1` | **Review extension mode.** Backend emits `receipt-review` v1 (`schemaName: "receipt-review"`, `schemaVersion: "1"`). |
| `X-Response-Schema` | Any other syntactically valid token (e.g., `receipt-review-v2`, `receipt-presentation-v2`) | **Unsupported version.** Rejected before body read (after auth check) with HTTP `406 Not Acceptable` and empty body. |
| `X-Response-Schema` | Empty after trimming HTTP optional whitespace, internal whitespace, > 96 bytes, or invalid token (`[A-Za-z0-9][A-Za-z0-9._-]*`) | **Malformed selection.** Rejected before body consumption with HTTP `400 Bad Request` and empty body. Duplicate headers and non-ASCII header bytes fail the earlier generic header check. Values are case-sensitive. |

Header precedence at HTTP ingress (`pipeline/real_receipt_http_service_v1.py`):

1. HTTP request line, framing, `Host`, and duplicate-header check -> `400 Bad Request`.
2. `Authorization: Bearer <token>` constant-time check -> `401 Unauthorized` (`WWW-Authenticate: Bearer`) before body consumption or version refusal.
3. `X-Response-Schema` syntax check (`400`) and supported-version check (`406 Not Acceptable`) before body consumption.
4. `Content-Length` limit check (`413`), `Content-Type` / `Content-Encoding` check (`415`), `X-Request-Id` / `X-Image-Id` check (`400`).

### 2.3 Content Type, Size, and Transport Behaviour

| Aspect | Presentation V1 (`receipt-presentation-v1`) | Review Extension (`receipt-review-v1`) |
| --- | --- | --- |
| HTTP response `Content-Type` (200) | `application/json` (strict UTF-8, no BOM) | `application/json` (strict UTF-8, no BOM) |
| Caching / connection headers | `Cache-Control: no-store`, `Connection: close` | `Cache-Control: no-store`, `Connection: close` |
| Max response payload bytes | `1,048,576` bytes (1 MiB) | `2,097,152` bytes (2 MiB) to accommodate multi-item `ocrEvidence` and `alternativeCandidates` |
| Empty-body HTTP refusals | `400`, `401`, `406`, `413`, `415`, `422`, `429`, `500`, `503`, `504` | Same empty-body HTTP refusals; note `406` added for unsupported `X-Response-Schema` |
| Processor `200` envelope outcomes | `RESULT_AVAILABLE`, `SOURCE_EVIDENCE_INSUFFICIENT`, `PROCESSING_FAILED` | Same V1 outcomes inside `presentation`, paired with `review` (`receiptDisposition` populated accordingly) |
| Runtime unavailable or quarantined | Empty `503` | Empty `503`. An explicit `PROCESSING_UNAVAILABLE` Presentation envelope is representable for fixtures with `review: null`. The proposed runtime uses the empty HTTP refusal. |

### 2.4 Client and Server Response Validation Requirements

Both Leng's Python egress validator and Tai's Android decoder MUST enforce fail-closed validation:

1. **Strict JSON lexical decoding:** Strict UTF-8 without BOM; single root JSON object; reject trailing content, comments, trailing commas, `NaN`/`Infinity`, unpaired surrogates, and duplicate object member names (before dictionary/map construction).
2. **Version check before payload mapping:** Require both `schemaName` and `schemaVersion` at the root and apply the V1 string-type checks at their respective paths. For a pair of strings other than `("receipt-review", "1")`, return `REJECT_UNSUPPORTED_SCHEMA_VERSION` at `$.schemaVersion` before payload mapping.
3. **Closed object member sets:** Every object in `"receipt-review"` v1 has a closed required member set. Missing members fail with `REJECT_MISSING_MEMBER`; unknown members fail with `REJECT_UNKNOWN_MEMBER`. Nullable fields MUST appear explicitly as JSON `null`.
4. **Embedded V1 validation:** Validate `"presentation"` against the exact unmodified Presentation V1 rules using the caller's `(expectedRequestId, expectedImageId, consumerMode)` context, prefixing error paths with `$.presentation`. Note: `"SYNTHETIC_FIXTURE"` is rejected in `"LIVE"` mode (`REJECT_SOURCE_MODE_MISMATCH`).
5. **No floating-point money/quantity rounding:** Decimal money and quantity values inside `review` (e.g., `observedUnitPriceMyr`, `bandLowMyr`, `bandHighMyr`) are validated as canonical plain decimal strings using exact decimal grammar and `Decimal`/`BigDecimal`, never binary floating point.
6. **Cross-section integrity:** Validate review member sets and local values, then resolve IDs, value/state consistency and cross-section references as in Section 3.9. Reject the entire response before UI mapping. A client binds the expected schema to the originating request. An unexpected wrapper or bare V1 response to a review request is a protocol error. An explicit new V1 request is the compatibility option.

Existing JSON, type, member and embedded V1 violations retain V1 error codes and paths (prefix embedded paths with `$.presentation`, leaving caller context paths under `$context`). The review validator adds `REJECT_INVALID_REVIEW_VALUE` for an invalid local value, `REJECT_INVALID_REVIEW_REFERENCE` for an unresolved, wrong-scope or ineligible ID/link, and `REJECT_REVIEW_STATE` for contradictory otherwise well-typed data, including probability, readiness and disposition. Resolve field/row and candidate IDs before comparing the selected record with its referenced value. Report the offending member path.

### 2.5 Exact byte budgets

Measure received or emitted response body bytes before any text conversion. The inclusive cap is 1,048,576 bytes for bare Presentation V1 and 2,097,152 bytes for the whole review wrapper, including outer whitespace. Reject an over-limit body as `REJECT_RESPONSE_TOO_LARGE` at `$`. Apply the HTTP cap while reading even if the declared length is absent or incorrect. Keep the original bounded UTF-8 bytes available for validation. For a review response, after strict lexical checks, version and root member checks, find the value of the unique top-level decoded key `presentation`. It must be an object. Its byte span starts at its opening ASCII `{` after the colon and any intervening JSON whitespace and ends immediately after its matching ASCII `}`. Count both braces and all bytes between them, including internal whitespace, literal multibyte characters and escaped spellings. Exclude surrounding whitespace, the property name and wrapper delimiters. Reject a span over 1,048,576 bytes as `REJECT_RESPONSE_TOO_LARGE` at `$.presentation` before embedded validation. Validate the original slice against strict V1 and the request context.

Python operates on the original `bytes`, Kotlin on the original `ByteArray`. After strict decode has checked UTF-8, grammar, duplicate decoded keys and Unicode scalar validity, either use verified byte offsets from the strict tokenizer or walk the original bytes. In the latter approach, iterate only top-level members, decode each key as a JSON string, skip the colon and the four JSON whitespace bytes, and use a delimiter stack for object and array values. Inside strings, ignore structural punctuation and skip the byte immediately following a backslash. Skip literals and numbers to the next delimiter outside strings. Keep a half-open byte range for the matching object. A nested property or matching word inside a string cannot identify the object. Character or UTF-16 indexes, reserialization and whitespace normalization cannot determine the limit. Python verifies the actual outbound bytes before sending. Android measures the actual inbound bytes using the same rule. An unexpected negotiated schema remains a protocol failure.

---

## 3. Complete `receipt-review` v1 Response Structure

### 3.1 Top-Level Envelope

```json
{
  "schemaName": "receipt-review",
  "schemaVersion": "1",
  "presentation": { "...": "exact ReceiptPresentationV1 object" },
  "review": null
}
```

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `schemaName` | `string` | Yes | No | Exact value `"receipt-review"`. |
| `schemaVersion` | `string` | Yes | No | Exact value `"1"`. |
| `presentation` | `object` | Yes | No | Exact `ReceiptPresentationV1` envelope (`schemaName: "receipt-presentation"`, `schemaVersion: "1"`, `sourceContractVersion: "0"`). |
| `review` | `object \| null` | Yes | Yes | `null` iff `presentation.outcome.status == "PROCESSING_UNAVAILABLE"`; non-null object for `RESULT_AVAILABLE`, `SOURCE_EVIDENCE_INSUFFICIENT`, and `PROCESSING_FAILED`. |

### 3.2 `review` Object (`ReviewExtensionV1`)

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `methodId` | `string` | Yes | No | Exact `"PROPOSED_RECEIPT_V1"` for this wrapper. A review request requires the configured seven-field runtime. |
| `methodVersion` | `string \| null` | Yes | Yes | Exact `"proposed-receipt-research-v1"` when `RESULT_AVAILABLE`, matching the embedded producer version. Null for fallback and failure. |
| `methodReadiness` | `string` | Yes | No | Enum: `"POLICY_APPLIED"`, `"NOT_READY"`, `"NOT_VALID"`, `"NOT_EVALUATED"`. |
| `receiptDisposition` | `string` | Yes | No | Enum: `"AUTO_RESOLVED"`, `"REVIEW_REQUIRED"`, `"UNVERIFIED_DRAFT"`, `"FALLBACK_NO_UPDATE"`, `"FAILED"`. |
| `failure` | `object \| null` | Yes | Yes | Non-null iff `receiptDisposition == "FAILED"`. Closed object with `stage: "PRE_RESOLUTION"` and `code` equal to the embedded V1 failure code. For embedded `PRESENTATION_PROJECTION_FAILURE`, the code may be refined to `PROPOSED_METHOD_FAILURE` for a retained method exception or `PROPOSED_CONFIGURATION_INVALID` for a recorded runtime configuration failure. The embedded retryable flag controls client guidance. |
| `region` | `string \| null` | Yes | Yes | Nonblank governed receipt region (e.g. `"W.P. Kuala Lumpur"`), or `null` when unspecified. |
| `ocrEvidence` | `object \| null` | Yes | Yes | Required if embedded source evidence contains token IDs. May be null for failure without a frame or source evidence. If a retained frame and completed OCR contain zero tokens, send the frame and `tokens: []`. |
| `fields` | `array<FieldReview>` | Yes | No | Ordered `FieldReview` objects (Section 3.5). Empty `[]` unless `presentation.outcome.status == "RESULT_AVAILABLE"`. |
| `pantryMappings` | `array<PantryMapping>` | Yes | No | One record per presented item row in order for `RESULT_AVAILABLE`, including explicit unavailable states. Empty `[]` when there are no presented rows. |

### 3.3 Outcome-to-Review Cross-Object Matrix

| `presentation.outcome.status` | `review` | `methodReadiness` | `receiptDisposition` | `failure` | `fields` | `pantryMappings` |
| --- | --- | --- | --- | --- | --- | --- |
| `RESULT_AVAILABLE` (`PROPOSED_RECEIPT_V1`) | Non-null | `"POLICY_APPLIED"` | `"AUTO_RESOLVED"` or `"REVIEW_REQUIRED"` | `null` | Exact match to `presentation.receipt` fields | `len(itemRows)` |
| `RESULT_AVAILABLE` (`PROPOSED_UNVERIFIED_REVIEW_V1`) | Non-null | `"NOT_READY"` | `"UNVERIFIED_DRAFT"` | `null` | Exact match to `presentation.receipt` fields | `len(itemRows)` |
| `SOURCE_EVIDENCE_INSUFFICIENT` | Non-null | `"NOT_EVALUATED"` | `"FALLBACK_NO_UPDATE"` | `null` | `[]` | `[]` |
| `PROCESSING_FAILED` | Non-null | `"NOT_EVALUATED"` or `"NOT_VALID"` | `"FAILED"` | `{"stage":"PRE_RESOLUTION","code":...}` | `[]` | `[]` |
| `PROCESSING_UNAVAILABLE` | `null` | N/A | N/A | N/A | N/A | N/A |

Notes:

- `NOT_VALID` is used exactly for `failure.code == "PROPOSED_CONFIGURATION_INVALID"` in the failure row. Malformed or mismatched startup artifacts normally refuse startup and therefore have no receipt envelope. Other pre-resolution failures use `NOT_EVALUATED` in the wrapper.
- Inventory persistence failures belong to the downstream Android result, separate from the immutable backend decision.
- When `methodReadiness == "NOT_READY"`, `presentation.automaticExtraction.producer.producerId` MUST equal `"PROPOSED_UNVERIFIED_REVIEW_V1"`.
- When `methodReadiness == "POLICY_APPLIED"`, `presentation.automaticExtraction.producer.producerId` MUST equal `"PROPOSED_RECEIPT_V1"`.
- `"AUTO_RESOLVED"` is valid iff `methodReadiness == "POLICY_APPLIED"` and every entry in `review.fields` has `fieldDisposition == "AUTO_ACCEPTED"`.
- `"REVIEW_REQUIRED"` is valid iff `methodReadiness == "POLICY_APPLIED"` and at least one entry in `review.fields` has `fieldDisposition == "REVIEW_REQUIRED"`.

### 3.4 Original OCR Evidence and Receipt-Region Coordinate Frame (`ocrEvidence`)

```json
"ocrEvidence": {
  "coordinateFrame": {
    "origin": "TOP_LEFT",
    "unit": "SUBMITTED_IMAGE_PIXELS",
    "imageWidth": 1100,
    "imageHeight": 700
  },
  "tokens": [
    {
      "tokenId": "tok-v1-...",
      "originalText": "MLK",
      "polygon": [[120.0, 210.0], [190.0, 210.0], [190.0, 232.0], [120.0, 232.0]],
      "rawConfidence": 0.20
    }
  ]
}
```

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `coordinateFrame.origin` | `string` | Yes | No | Exact value `"TOP_LEFT"`. `+x` points right, `+y` points down. |
| `coordinateFrame.unit` | `string` | Yes | No | Exact value `"SUBMITTED_IMAGE_PIXELS"`. Matches exact decoded PNG dimensions submitted for `presentation.imageId`. |
| `coordinateFrame.imageWidth` | `integer` | Yes | No | Integer in `[1, 1600]`, matching the PNG admission limit. |
| `coordinateFrame.imageHeight` | `integer` | Yes | No | Integer in `[1, 1600]`, matching the PNG admission limit. |
| `tokens` | `array<OcrToken>` | Yes | No | Ordered array whose `tokenId` sequence MUST equal `presentation.sourceEvidence.tokenIds` element-for-element. |
| `tokens[i].tokenId` | `string` | Yes | No | Opaque protocol ID matching `presentation.sourceEvidence.tokenIds[i]`. |
| `tokens[i].originalText` | `string` | Yes | No | Non-empty literal OCR transcription. Preserve exact Unicode scalar values, whitespace and case. The source gate's text and region bounds also apply to the wrapper (Section 3.9). |
| `tokens[i].polygon` | `array<[number, number]>` | Yes | No | `3` to `8` finite `[x, y]` coordinate pairs satisfying `0 <= x <= imageWidth`, `0 <= y <= imageHeight`, with `>= 2` distinct `x` and `>= 2` distinct `y` values. |
| `tokens[i].rawConfidence` | `number \| null` | Yes | Yes | Finite IEEE-754 binary64 raw OCR score (in `[0, 1]` when produced by PaddleOCR), or `null`. Never treated as calibrated field probability. |

**Receipt-region crop behaviour on Android:** Android crops/previews the receipt locally before encoding the submitted PNG (`imageId`). Therefore `(imageWidth, imageHeight)` and all `polygon` vertices share the exact pixel coordinate space of Android's locally retained cropped PNG for `imageId`. For any field or alternative candidate, Android computes the bounding rectangle `[min(x), min(y), max(x), max(y)]` across its referenced `sourceTokenIds` (adding UI padding clamped to `[0, imageWidth] x [0, imageHeight]`) directly on the locally stored cropped bitmap. No cropped sub-images are transmitted by the backend.

The producer retains width and height from the validated recognition record before OCR projection. For LIVE review, both sides bind expected width and height to the exact submitted PNG when registering the request. Under fixture validation, both expected dimensions may be omitted or supplied together. Whenever an OCR frame is present and expected dimensions are supplied, mismatch is `REJECT_INVALID_REVIEW_REFERENCE` at the first differing member under `$.review.ocrEvidence.coordinateFrame`, width before height. In LIVE mode a frame requires both expected dimensions. If the exact submitted image was deleted after processing, retain validated dimensions with any retained evidence and mark crop inspection unavailable. The original acquisition image is a separate object and cannot substitute for the submitted frame. OCR literals are delivered only to the authenticated submitting client under the runtime privacy policy.

### 3.5 Field Review Record (`review.fields[i]`)

`review.fields` covers **all seven receipt field roles** in exact normative `PresentationReceipt` order:

1. Receipt-level fields (`itemRowId: null`): `STORE_NAME`, `PURCHASE_DATE`, `RECEIPT_TOTAL`.
2. Item-row fields (`itemRowId: row.rowId`): for each `row` in `presentation.receipt.itemRows`, in exact array order: `ITEM_DESCRIPTION`, `QUANTITY`, `UNIT_PRICE`, `LINE_TOTAL`.

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `fieldId` | `string` | Yes | No | Exact match to corresponding `PresentationField.fieldId`. |
| `itemRowId` | `string \| null` | Yes | Yes | `null` for `STORE_NAME`, `PURCHASE_DATE`, `RECEIPT_TOTAL`; exact `row.rowId` for item roles. |
| `role` | `string` | Yes | No | Exact match to `PresentationField.role` (`STORE_NAME`, `PURCHASE_DATE`, `ITEM_DESCRIPTION`, `QUANTITY`, `UNIT_PRICE`, `LINE_TOTAL`, `RECEIPT_TOTAL`). |
| `optionalWhenMissing` | `boolean` | Yes | No | `true` iff `role == "UNIT_PRICE"`; `false` for all other six roles. |
| `originalB2` | `object` | Yes | No | Immutable B2 `c0` extraction record (`OriginalB2Record`). |
| `selectedPreReview` | `object` | Yes | No | Immutable backend pre-review selection (`SelectedPreReviewRecord`). |
| `fieldDisposition` | `string` | Yes | No | Enum: `"AUTO_ACCEPTED"`, `"REVIEW_REQUIRED"`, `"UNVERIFIED_DRAFT"`. |
| `automaticCommitPermitted` | `boolean` | Yes | No | `true` iff `fieldDisposition == "AUTO_ACCEPTED"`. This is the methodology's pre-resolution policy flag. Every actual inventory write requires the separate explicit Android confirmation in Section 5. |
| `calibratedProbability` | `number \| null` | Yes | Yes | Calibrated correctness probability in `[0, 1]` for `selectedPreReview.candidateId`, or `null` when unavailable. |
| `probabilityAvailable` | `boolean` | Yes | No | `true` iff `calibratedProbability != null`. Must be `false` for `"UNVERIFIED_DRAFT"`. |
| `probabilityUnavailableReason` | `string \| null` | Yes | Yes | `null` iff `probabilityAvailable == true`; nonblank privacy-safe reason/code otherwise. |
| `unresolvedConflict` | `boolean \| null` | Yes | Yes | Actual cached policy conflict flag when policy evaluation computed it. Null when it did not run for the field. Python retains the flag alongside the verification audit, including if the final projection reverts a candidate. Android never infers it from price alone or alternative count. |
| `suspicionReasons` | `array<string>` | Yes | No | Unique enum codes from `SuspicionReasonCode` (Section 3.7). Empty `[]` when clean. |
| `correctionReason` | `string` | Yes | No | Final verifier reason, including any downstream reversion, or `EMPIRICAL_POLICY_UNAVAILABLE` for `NOT_READY`. Use a fixed privacy-safe public code. |
| `developmentRecommendation` | `object \| null` | Yes | Yes | Optional non-policy preview recommendation from `correct_receipt_v1` (Section 3.5.3). |
| `retailerEvidence` | `object` | Yes | No | `RetailerEvidence` for selected value/context (Section 3.6). |
| `priceEvidence` | `object` | Yes | No | `PriceEvidence` for selected value/row context (Section 3.6). |
| `alternativeCandidates` | `array<AlternativeCandidate>` | Yes | No | Up to 127 non-`c0` candidates with a retained constraint audit (Section 3.5.4), within the configured candidate limit and in retained candidate order. |

#### 3.5.1 `OriginalB2Record` (`originalB2`)

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `c0CandidateId` | `string` | Yes | No | Opaque protocol ID for permanent `c0` (distinct from all `alternativeCandidates[*].candidateId`). |
| `status` | `string` | Yes | No | Enum: `"EXTRACTED"`, `"MISSING"`, `"UNRESOLVED"`. Exact original B2 `StructuredField.status`. |
| `value` | `string \| null` | Yes | Yes | Exact original B2 `StructuredField.value` (`c0`), nonblank iff `status == "EXTRACTED"`, else `null`. |
| `canonicalValue` | `string \| null` | Yes | Yes | Canonical V1 presentation form of `value` iff `status == "EXTRACTED"` and valid under V1 grammar, else `null`. |
| `absenceReason` | `string \| null` | Yes | Yes | `null` iff `status == "EXTRACTED"`; nonblank privacy-safe reason iff `status != "EXTRACTED"`. |
| `sourceTokenIds` | `array<string>` | Yes | No | Unique token IDs resolving to `ocrEvidence.tokens`; non-empty if `status == "EXTRACTED"`. |
| `nativeConfidence` | `number \| null` | Yes | Yes | Finite binary64 native B2 confidence (or `null`); must be `null` if `status != "EXTRACTED"`. |
| `candidateStatus` | `string` | Yes | No | `SCORING_ELIGIBLE` or `CONSTRAINT_REJECTED` from the c0 audit. The latter still allows retention for review. |
| `constraintReasons` | `array<string>` | Yes | No | Non-empty unique privacy-safe codes for `CONSTRAINT_REJECTED`, otherwise `[]`. |
| `calibratedProbability` | `number \| null` | Yes | Yes | Calibrated probability in `[0, 1]` for `c0` if `methodReadiness == "POLICY_APPLIED"` and `c0` was scored/calibrated, else `null`. |
| `probabilityAvailable` | `boolean` | Yes | No | `true` iff `originalB2.calibratedProbability != null`. |

#### 3.5.2 `SelectedPreReviewRecord` (`selectedPreReview`)

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `candidateId` | `string` | Yes | No | Equals `originalB2.c0CandidateId` OR one `alternativeCandidates[k].candidateId` whose `candidateStatus == "SCORING_ELIGIBLE"`. |
| `status` | `string` | Yes | No | Must equal `PresentationField.status`. |
| `value` | `string \| null` | Yes | Yes | Must equal `PresentationField.originalAutomaticValue`. |
| `canonicalValue` | `string \| null` | Yes | Yes | Must equal `PresentationField.presentationValue`. |
| `absenceReason` | `string \| null` | Yes | Yes | Must equal `PresentationField.absenceReason`. |
| `sourceTokenIds` | `array<string>` | Yes | No | Must equal `PresentationField.sourceTokenIds`. |
| `changedFromC0` | `boolean` | Yes | No | `true` iff `candidateId != originalB2.c0CandidateId`. |

#### 3.5.3 `DevelopmentRecommendation` (`developmentRecommendation`)

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `recommendation` | `string` | Yes | No | Enum: `"CORRECT"`, `"RETAIN"`, `"REVIEW_REQUIRED"`. |
| `recommendedCandidateId` | `string` | Yes | No | Must equal `originalB2.c0CandidateId` or one `alternativeCandidates[k].candidateId`. |
| `reason` | `string` | Yes | No | Nonblank privacy-safe reason from `correct_receipt_v1`. |

When `methodReadiness == "NOT_READY"` (`UNVERIFIED_DRAFT`), `selectedPreReview` MUST retain `originalB2` (`c0`), while `developmentRecommendation` MAY highlight an unverified recommendation for user inspection without auto-selecting it.

#### 3.5.4 `AlternativeCandidate` (`alternativeCandidates[k]`)

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `candidateId` | `string` | Yes | No | Unique protocol ID within field, distinct from `originalB2.c0CandidateId`. |
| `value` | `string` | Yes | No | Nonblank candidate value. |
| `canonicalValue` | `string \| null` | Yes | Yes | V1 presentation form of the exact candidate `value` when representable, otherwise null. An unrepresentable alternative remains inspectable and cannot be accepted directly. A selected alternative must be representable or existing presentation failure handling applies. |
| `candidateStatus` | `string` | Yes | No | Enum: `"SCORING_ELIGIBLE"`, `"CONSTRAINT_REJECTED"`, `"REJECTED_PRICE_ONLY"`. |
| `constraintReasons` | `array<string>` | Yes | No | Non-empty unique privacy-safe strings iff `candidateStatus == "CONSTRAINT_REJECTED"`; `[]` otherwise. |
| `replacementSupport` | `array<string>` | Yes | No | Unique non-price support codes (e.g., `"ROLE_BOUND_SOURCE"`, `"EXACT_RECEIPT_ARITHMETIC"`, `"RETAILER_MAPPING"`, `"PANTRY_TERMINOLOGY"`, `"EXPLICIT_DATE_ANCHOR"`); `[]` for rejected candidates. |
| `preliminaryRank` | `integer` | Yes | No | One-based index in the retained non-c0 array. The producer preserves retained order, including when the date graph supplies no numeric rank. It does not sort by probability or price. |
| `calibratedProbability` | `number \| null` | Yes | Yes | Finite number in `[0, 1]` or `null`. MUST be `null` whenever `candidateStatus != "SCORING_ELIGIBLE"` or `methodReadiness != "POLICY_APPLIED"`. |
| `probabilityAvailable` | `boolean` | Yes | No | `true` iff `calibratedProbability != null`. |
| `sourceTokenIds` | `array<string>` | Yes | No | Unique token aliases for the candidate's output linkage, copied from its retained output token IDs. A selected alternative must have at least one. |
| `sourceReferences` | `array<SourceReference>` | Yes | No | Non-empty array of `SourceReference` records. |
| `retailerEvidence` | `object` | Yes | No | `RetailerEvidence` evaluated for this candidate. |
| `priceEvidence` | `object` | Yes | No | `PriceEvidence` evaluated for this candidate. |

`SourceReference` (closed member set):

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `sourceKind` | `string` | Yes | No | Enum: `"SOURCE_TOKEN_OR_NEIGHBOUR"`, `"GENERIC_NORMALIZATION"`, `"RETAILER_MAPPING"`, `"PANTRY_TERMINOLOGY"`. (`"ORIGINAL"` belongs only to `c0`.) |
| `reference` | `string` | Yes | No | Nonblank opaque seed/entry/span identifier (no raw paths/URIs/protected markers). |
| `observedValue` | `string \| null` | Yes | Yes | Nonblank literal observed surface text or `null`. |
| `sourceTokenIds` | `array<string>` | Yes | No | Unique token IDs resolving to `ocrEvidence.tokens`. |
| `characterSpans` | `array<CharacterSpan>` | Yes | No | Each closed span contains `tokenId`, integer `start`, integer `end`, and `text`. Offsets are zero-based half-open **Unicode code-point** offsets. Require `0 <= start < end <= codePointCount(originalText)`, `tokenId` in the parent `sourceTokenIds`, and the exact code-point slice as `text`. Kotlin converts code-point offsets to UTF-16 indexes before taking the substring. |
| `resourceReference` | `string \| null` | Yes | Yes | Versioned snapshot reference `"<resource_id>@<version>:sha256:<64hex>"` for `RETAILER_MAPPING` / `PANTRY_TERMINOLOGY`; `null` otherwise. |

### 3.6 Retailer and Price Evidence Objects

#### `RetailerEvidence`

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `status` | `string` | Yes | No | Enum: `"SUPPORTED"`, `"UNAVAILABLE"`, `"NOT_APPLICABLE"`. |
| `retailerId` | `string \| null` | Yes | Yes | Resolved opaque retailer key (e.g. `"lotuss:pricecatcher:176"`) when resolved, else `null`. |
| `sourceReferences` | `array<object>` | Yes | No | Array of `{"resourceReference": str, "entryId": str}`; non-empty iff `status == "SUPPORTED"`. |
| `reason` | `string` | Yes | No | Nonblank privacy-safe code/reason (e.g. `"RETAILER_MAPPING_MATCHED"`, `"NO_APPLICABLE_RETAILER_SUPPORT"`, `"RETAILER_SNAPSHOT_UNAVAILABLE"`, `"NOT_APPLICABLE_ROLE"`). |

#### `PriceEvidence`

| Member | Type | Required | Nullable | Rules |
| --- | --- | --- | --- | --- |
| `status` | `string` | Yes | No | Enum: `"PRICE_SUPPORTED"`, `"PRICE_CONFLICT"`, `"PRICE_UNAVAILABLE"`, `"PRICE_INCONCLUSIVE"`, `"NOT_APPLICABLE"`. |
| `reason` | `string` | Yes | No | Fixed privacy-safe code, including `"WITHIN_CONFIGURED_BAND"`, `"OUTSIDE_CONFIGURED_BAND"`, `"PRICE_SNAPSHOT_UNAVAILABLE"`, `"NO_MATCHING_PRICE"`, `"ITEM_PROMOTION"`, `"PROMOTION_SCOPE_UNSPECIFIED"` and `"NOT_AN_ITEM_FIELD"`. |
| `observedUnitPriceMyr` | `string \| null` | Yes | Yes | Canonical MYR money string (`^(0|[1-9][0-9]*)\.[0-9]{2}$`) when evaluated, else `null`. |
| `priceBasis` | `string \| null` | Yes | Yes | Enum: `"EACH"`, `"KG"`, `"G"`, `"LB"`, `"OZ"`, or `null`. |
| `bandLowMyr` | `string \| null` | Yes | Yes | Canonical MYR money string iff `status in {"PRICE_SUPPORTED", "PRICE_CONFLICT", "PRICE_INCONCLUSIVE"}` with single band, else `null`. |
| `bandHighMyr` | `string \| null` | Yes | Yes | Canonical MYR money string (`Decimal(bandLowMyr) <= Decimal(bandHighMyr)`) when `bandLowMyr != null`, else `null`. |
| `ruleId` | `string \| null` | Yes | Yes | Discrepancy rule identifier when price lookup ran with configured rule, else `null`. |
| `resourceReference` | `string \| null` | Yes | Yes | Versioned snapshot reference (`<resource_id>@<version>:sha256:<64hex>`) when price snapshot exists, else `null`. |
| `entryIds` | `array<string>` | Yes | No | Matched price-band entry IDs (unique nonblank strings); non-empty for `PRICE_SUPPORTED` / `PRICE_CONFLICT`. |
| `sourceTokenIds` | `array<string>` | Yes | No | Unique token IDs for observed unit price resolving to `ocrEvidence.tokens`. |

`PRICE_SUPPORTED` and `PRICE_CONFLICT` require an observed amount, basis, both band endpoints, rule ID, resource reference, exactly one entry ID and linked unit-price tokens. `PRICE_INCONCLUSIVE` may retain the same facts when the issue is applicability, or partial references when no single band applies. In that case both band endpoints are null. `PRICE_UNAVAILABLE` has no observed comparison or band. `NOT_APPLICABLE` has null scalar evidence and empty ID arrays. A rejected item candidate without a price evaluation reports `PRICE_UNAVAILABLE` with a fixed reason such as `PRICE_NOT_ASSESSED`. If the final research audit reverts for `PRICE_CONTEXT_CHANGED`, the wrapper exposes that comparison as inconclusive, preserving the original context-specific evidence privately. A price conflict is evidence of a discrepancy and cannot establish a product identity or select a correction.

Retailer support comes from the retained retailer feature and exact approved terminology entries. Preserve evidence under the candidate and receipt context in which it was computed. Missing or conflicting terms never become positive support. Snapshot references are immutable versioned resource IDs and hashes. Resource entry IDs are opaque scoped keys and may contain colons. They are distinct from protocol aliases, which follow the Presentation V1 identifier grammar. Source URLs, file paths and records outside the current receipt stay in backend custody.

Translate internal price reason `REFERENCE_PROMOTION_UNSPECIFIED` to `PROMOTION_SCOPE_UNSPECIFIED` and `AMBIGUOUS_PRICE_REFERENCE` to `AMBIGUOUS_PRICE_BAND` for the wire. Other internal reasons must pass the public code and privacy checks before projection. If no approved public code applies, use `DETAIL_UNAVAILABLE` and retain the full reason in the backend audit.

### 3.7 Enumerated State Registers

- `SuspicionReasonCode`: `"LOW_OCR_CONFIDENCE"`, `"LOW_EXTRACTOR_CONFIDENCE"`, `"MISSING_REQUIRED_CONTENT"`, `"PARSE_TYPE_FAILURE"`, `"LINE_ASSOCIATION_CONFLICT"`, `"ARITHMETIC_CONTRADICTION"`.
- `methodReadiness`: `"POLICY_APPLIED"`, `"NOT_READY"`, `"NOT_VALID"`, `"NOT_EVALUATED"`.
- `receiptDisposition`: `"AUTO_RESOLVED"`, `"REVIEW_REQUIRED"`, `"UNVERIFIED_DRAFT"`, `"FALLBACK_NO_UPDATE"`, `"FAILED"`.
- `fieldDisposition`: `"AUTO_ACCEPTED"`, `"REVIEW_REQUIRED"`, `"UNVERIFIED_DRAFT"`.
- `candidateStatus`: `"SCORING_ELIGIBLE"`, `"CONSTRAINT_REJECTED"`, `"REJECTED_PRICE_ONLY"`.
- `sourceKind`: `"SOURCE_TOKEN_OR_NEIGHBOUR"`, `"GENERIC_NORMALIZATION"`, `"RETAILER_MAPPING"`, `"PANTRY_TERMINOLOGY"`.
- `mappingStatus`: `"MAPPED"`, `"AMBIGUOUS"`, `"UNRESOLVED"`, `"RESOURCE_UNAVAILABLE"`.

### 3.8 Separate Pantry Semantic Mapping (`pantryMappings`)

`pantryMappings` is strictly separated from `fields` (`ITEM_DESCRIPTION`) so primary receipt text extraction and pantry-normalised product identity are never conflated:

```json
{
  "rowId": "row-001",
  "descriptionFieldId": "fld-001-desc",
  "mappingStatus": "MAPPED",
  "selectedIdentity": {
    "entryId": "item:1559",
    "pantryIdentity": "pricecatcher:item:1559",
    "pantryCategory": "SAYUR-SAYURAN",
    "referenceUnit": "1kg",
    "resourceReference": "my-pricecatcher-kl-terminology@1:sha256:..."
  },
  "candidateIdentities": [
    {
      "entryId": "item:1559",
      "pantryIdentity": "pricecatcher:item:1559",
      "pantryCategory": "SAYUR-SAYURAN",
      "referenceUnit": "1kg",
      "resourceReference": "my-pricecatcher-kl-terminology@1:sha256:..."
    }
  ]
}
```

| Status | `selectedIdentity` | `candidateIdentities` |
| --- | --- | --- |
| `"MAPPED"` | Non-null, equals `candidateIdentities[0]` | Length `1` |
| `"AMBIGUOUS"` | `null` | Length `>= 2` |
| `"UNRESOLVED"` | `null` | `[]` |
| `"RESOURCE_UNAVAILABLE"` | `null` | `[]` |

Each closed `PantryMapping` contains the five members shown. `rowId` and `descriptionFieldId` match the embedded item row and its description field. `selectedIdentity` is nullable. Each closed identity has nonblank `entryId`, `pantryIdentity` and versioned `resourceReference`, plus nullable nonblank `pantryCategory` and `referenceUnit`. Resolve terminology against the final issued receipt description with the applicable retailer scope. A missing description yields `UNRESOLVED` if the resource is available. With no resource, use `RESOURCE_UNAVAILABLE`. Group exact matches by `pantryIdentity`, retain the first in snapshot order per identity, and preserve that order for display. A unique match is a semantic suggestion. Prices alone cannot create one. If the user changes or rejects the description, Android clears any staged identity bound to the former description. Inventory can use the confirmed description without an identity if mapping remains unavailable or ambiguous.

### 3.9 Cross-Field Reference Integrity & Backend-Audit Exclusions

**Reference integrity rules (enforced by both Python egress and Android validator):**

1. `ocrEvidence.tokens` token IDs equal `presentation.sourceEvidence.tokenIds` in exact order.
2. `review.fields` aligns 1-to-1 in exact order with `presentation.receipt.receiptFields` followed by `presentation.receipt.itemRows[*].fields` (`fieldId`, `role`, `itemRowId`).
3. All `sourceTokenIds` arrays resolve to `ocrEvidence.tokens`. Use the same opaque aliases as V1 for fields, rows and OCR. Candidate IDs are response-scoped protocol aliases, unique across all fields and candidate records in the response. The LIVE producer allocates aliases `cand-v1-<namespace>-<ordinal>` from the same V1 attempt namespace, counting from 1 with c0 first for each field in Section 3.5 order. Allocate all aliases before projecting links. Persist references with request and image IDs. A new attempt gets its own identity and candidate aliases.
4. Validate every span against its parent token list and the exact code-point slice. Validate at most 128 OCR tokens, 256 code points and 1,024 UTF-8 bytes per token, 16,384 code points and 49,152 UTF-8 bytes total, and at most 1,024 vertices in total.
5. `selectedPreReview` matches the corresponding `PresentationField` (`status`, `originalAutomaticValue`, `presentationValue`, `absenceReason`, `sourceTokenIds`).
6. `selectedPreReview.candidateId` resolves within its field. For c0, selected status, raw and canonical values, absence reason and token IDs equal the corresponding original B2 members. For an alternative, require `SCORING_ELIGIBLE`, nonempty non-price replacement support, `EXTRACTED`, and exact equality with that candidate's value, canonical value and output token IDs.
7. `developmentRecommendation.recommendedCandidateId` (when non-null) equals `originalB2.c0CandidateId` or an `alternativeCandidates[k].candidateId`.
8. `probabilityAvailable` is true exactly when the associated probability is non-null. In `NOT_READY`, every field is `UNVERIFIED_DRAFT` and all probabilities and conflict flags are null. Every selected candidate is its c0. In `POLICY_APPLIED`, every field is `AUTO_ACCEPTED` or `REVIEW_REQUIRED`. Automatic acceptance requires a representable extracted value, eligible candidate, valid probability, and cached conflict false. A known conflict requires review. If the field's final probability is unavailable, retain c0 and require review. Its earlier audit probability may still be inspectable after a documented joint reversion. Otherwise the field probability equals the selected candidate's calibrated probability. Rejected candidates and ineligible c0 records have null probability. For a selected alternative, c0 also needs a valid comparison probability.
9. `pantryMappings` aligns 1-to-1 in order with `presentation.receipt.itemRows` (`rowId`, `descriptionFieldId = row.fields[0].fieldId`).
10. All reason/detail strings MUST satisfy Presentation V1's privacy-safe reason validation (`REJECT_UNSAFE_PROVENANCE`). Wrapper-specific reasons are fixed public codes matching `[A-Z][A-Z0-9_]{0,63}`. Reused V1 absence reasons retain V1's original grammar. Never copy exception messages or raw OCR into reason fields.

**Kept strictly in backend audit only (excluded from Android JSON):**

- Raw uncalibrated model logits (`raw_score`) and scorer coefficients/weights (`FrozenScorer.weights`).
- Seven-slot feature vectors and missingness masks (`q_o, q_e, a_l, a_y, s_r, s_a, s_p`).
- `FitConfiguration`, `membership_sha256`, `training_examples_sha256`, `validation_predictions_sha256`.
- Limit-overflow candidates (`LIMIT_OVERFLOW`) and raw `B3CompatibleSeedV1` records.
- Internal SHA-256 decision evidence digests and local filesystem snapshot paths/URLs.

---

## 4. Correction, Calibration, and Evidence Semantics

### 4.1 Nine-Way Value & State Distinction

| Concept | Authoritative Location | Mutability | Semantic Meaning |
| --- | --- | --- | --- |
| **OCR-recognized text** | `review.ocrEvidence.tokens[i].originalText` | Immutable | Literal text returned by PaddleOCR for one bounding polygon. |
| **B2 original `c0`** | `field.originalB2` | Immutable | Initial layout-aware B2 structured extraction before any rule/proposed change. |
| **Development recommendation** | `field.developmentRecommendation` | Immutable | Non-calibrated preview recommendation from `correct_receipt_v1`; advisory only, never an automatic commit or policy decision. |
| **Selected pre-review automatic value** | `field.selectedPreReview` & `presentation.receipt` | Immutable | The backend output transmitted for the receipt before human interaction (`c*` if `POLICY_APPLIED`, `c0` if `NOT_READY`). |
| **Policy-verified decision** | `fieldDisposition in {"AUTO_ACCEPTED","REVIEW_REQUIRED"}` when `methodReadiness == "POLICY_APPLIED"` | Immutable | Result of frozen `Theta_A`, `Kappa`, and `Phi` selective verification (`AUTO_ACCEPTED` permits auto-commit; `REVIEW_REQUIRED` blocks auto-commit). |
| **Unverified draft** | `methodReadiness == "NOT_READY"`, `receiptDisposition == "UNVERIFIED_DRAFT"`, `fieldDisposition == "UNVERIFIED_DRAFT"` | Immutable | Operational B2 draft served when verification artifacts are absent; never labeled policy-verified. |
| **Unresolved field** | Extraction: `status == "UNRESOLVED"` (`value: null`); User review: `userReviewState == "UNRESOLVED"` | Extraction immutable; review state mutable until confirmation | Distinct from `MISSING` optional `UNIT_PRICE` and distinct from `"AUTO_ACCEPTED"`. |
| **User-edited value** | Android-local review model (`USER_MODIFIED`) | Mutable during review until confirmation | Applied user edit, including an edit that equals a backend value. The backend evidence stays unchanged. |
| **Final user-approved value** | Immutable Android-local confirmation payload and committed outcome | Published once per confirmation identity | Explicitly approved inventory value, with complete purchase history only in the history-saving mode. User action remains separate from automatic accuracy. |

### 4.2 Confidence vs. Calibrated Probability

- `ocrEvidence.tokens[i].rawConfidence`: Raw native OCR score from PaddleOCR (`[0, 1]` or `null`).
- `originalB2.nativeConfidence` preserves B2's native extractor confidence. Embedded `PresentationField.nativeConfidence` is null on policy output and carries the B2 value in an unverified draft. These may differ for the same field.
- `calibratedProbability`: Output of frozen validation calibration `Kappa` over `Theta_A` raw scores, constrained to `[0, 1]`.
- **Prohibition:** When `Kappa` is absent (`NOT_READY`), invalid (`NOT_VALID`), or unavailable for a specific field (`ORIGINAL_NOT_SCORING_ELIGIBLE`, `CALIBRATION_UNAVAILABLE`, `CONSTRAINT_REJECTED`, `REJECTED_PRICE_ONLY`), `calibratedProbability` MUST be JSON `null` and `probabilityAvailable` MUST be `false`. Raw logits, heuristic edit similarities, and evidence counts MUST NEVER be transmitted or labeled as `calibratedProbability`.

### 4.3 Edge-Case Semantics

- **Retained original values:** `selectedPreReview.candidateId == originalB2.c0CandidateId`, `changedFromC0 == false`. Still undergoes full `Phi` policy checks; may be `AUTO_ACCEPTED` or `REVIEW_REQUIRED`.
- **Selected alternative candidates:** The producer uses the current method's calibrated comparison with c0, frozen replacement margin and preconditions. It projects the final selection after any joint arithmetic or price-context reversion. Selection and disposition are independent. A selected alternative can still require review. Android validates the result and does not rerun comparisons or thresholds.
- **Rejected or ineligible candidates:** Marked `CONSTRAINT_REJECTED` (with `constraintReasons`) or `REJECTED_PRICE_ONLY` (price was sole support over `c0`); retain `calibratedProbability: null` and `probabilityAvailable: false`; cannot be selected by `selectedPreReview`.
- **Missing original values (`status == "MISSING"`):** `originalB2.value == null`; `c0` is not `SCORING_ELIGIBLE` (`probabilityAvailable: false`). In `POLICY_APPLIED` mode, `fieldDisposition` MUST be `"REVIEW_REQUIRED"` with `probabilityUnavailableReason: "ORIGINAL_NOT_SCORING_ELIGIBLE"`. Application eligibility is mode-specific in Section 5.4. A legitimately absent optional unit price can remain null in receipt history.
- **Missing supporting evidence:** Missing retailer snapshot (`retailerEvidence.status == "UNAVAILABLE"`) or missing price snapshot/band (`priceEvidence.status == "PRICE_UNAVAILABLE"`) is preserved as unavailable, NEVER treated as negative evidence or a forced failure/review trigger on its own.
- **Conflicting evidence:** A true cached conflict requires review. The decoder displays a recorded price conflict independently and follows the supplied field disposition.
- **Price evidence states:**
  - `PRICE_SUPPORTED`: Observed MYR unit price lies within `[low * (1 - tol), high * (1 + tol)]`. Plausibility signal only; cannot prove product identity or authorize candidate replacement without non-price support (`REJECTED_PRICE_ONLY` enforces this).
  - `PRICE_CONFLICT`: Outside band where reference promotion scope is documented (`NON_PROMOTIONAL`). Contradiction signal only; cannot alone reject `c0` without non-price evidence.
  - `PRICE_UNAVAILABLE`: Snapshot missing, retailer/date/region unresolved, or no matching band. Represent the missing price feature as null.
  - `PRICE_INCONCLUSIVE`: Promotion/adjustment detected on item row, weight basis unresolved, ambiguous product/band match, or out-of-band with `UNSPECIFIED` promotion scope. Represent the missing price feature as null. Missingness is separate from an observed negative comparison.
- **Source-gate fallback & pre-resolution technical failure:** Never invent receipt fields or probabilities (`fields: []`); `FALLBACK_NO_UPDATE` (`SOURCE_EVIDENCE_INSUFFICIENT`) triggers recapture/manual entry guidance; `FAILED` (`PRE_RESOLUTION`) surfaces retryable/non-retryable error state.

### 4.4 Exact quantities and independent unit evidence

The primary receipt `QUANTITY` remains a positive, canonical decimal string with zero to three fractional digits. Preserve its exact value and presented scale. An actual printed unit can be inspected in the literal source text when it occurs in an OCR token or span linked to that quantity. The existing OCR and source-reference members preserve that literal evidence. This revision adds no structured unit member or eighth field. A unit outside the linked quantity evidence is not presented as an extracted quantity unit. The user may inspect the exact submitted image when available.

The purchase quantity is receipt-derived or explicitly edited. A printed quantity unit is source evidence. Price `priceBasis` qualifies the price comparison, and pantry `referenceUnit` qualifies the terminology resource. Neither supplies a purchased quantity unit or a default inventory unit. The inventory unit is an Android-local user-confirmed choice for each included row, even when a visible source literal is available to inform that choice. Where the source unit is missing or ambiguous, ask the user to choose a compatible supported unit. Never fill a unit from the price or pantry record. Keep any literal source unit separate from the user-confirmed value. Confirmation can use that value for stock without retroactively treating it as receipt evidence.

---

## 5. Android Review Interaction and Confirmation State Machine

Tai owns the Android decoder, Inventory-First Sage V5 review, and local confirmation and persistence. Keep inventory-first launch, compact inventory header, floating scan action, source-selection bottom sheet, full-screen crop, and the existing Preview, Details and collapsible Review flow, without a permanent navigation bar. Android review and confirmation state is local and is outside the extraction endpoint and wire response.

### 5.1 Android Field-Level User-Review States

For every field in `review.fields` (and item rows containing them), Android maintains a separate mutable review state layered over the immutable `presentation` + `review` DTO:

- **`UNREVIEWED`**: Initial state of every field. A valid extracted `AUTO_ACCEPTED` value is pre-staged for the final receipt tap with its policy label. Review-required and unverified values appear as suggestions pending user action.
- **`USER_CONFIRMED`**: User explicitly accepted either `selectedPreReview`, `originalB2` (`c0`), or a specific candidate from `alternativeCandidates`.
- **`USER_MODIFIED`**: User explicitly applied a valid custom value. The action records a user edit even if its value equals an OCR or candidate value.
- **`USER_REJECTED`**: User explicitly rejected the field/proposed correction without approving any replacement.
- **`UNRESOLVED`**: User explicitly leaves the field unresolved. Clears any staged or accepted approval, including an initial `AUTO_ACCEPTED` value. Only a subsequent explicit Accept or valid Edit can approve that field. Its relevance to confirmation depends on the mode.

### 5.2 Action State Transitions

| Action | Required Input | Resulting `userReviewState` | Effect on Displayed Value | Effect on Confirmation Eligibility | Immutable Evidence Preserved |
| --- | --- | --- | --- | --- | --- |
| **Accept** | Explicit source enum `SELECTED_PRE_REVIEW`, `ORIGINAL_B2_C0`, or `ALTERNATIVE` and a matching candidate ID within the field. A directly selectable value needs a valid non-null canonical value. An alternative also needs `SCORING_ELIGIBLE`. Null is permitted only for an explicitly accepted `UNIT_PRICE/MISSING` from the selected or original record. | `USER_CONFIRMED` | Displays the accepted value and its source. | Field becomes **ELIGIBLE**. | Keep the entire backend envelope immutable. |
| **Edit** | User applies a valid value using the field grammar from Section 3.5. An explicit edit can clear optional unit price to null. | `USER_MODIFIED` | Displays the locally edited value with a user-edit label. | Applies to the selected mode. Pending or invalid input for a required field blocks it until applied or discarded. Clearing a value alone does not establish legitimate absence for history. | Keep the backend envelope immutable. |
| **Reject** | User explicitly rejects the field or proposed correction. | `USER_REJECTED` | Shows the rejected choice and offers original, another eligible candidate or edit. | Clears approval. Blocks a field required by the selected mode until an explicit Accept or valid Edit. | Retain the rejection as a local action and preserve the backend envelope. |
| **Leave unresolved** | User explicitly chooses to leave the field unresolved. | `UNRESOLVED` | Shows the unresolved label with the original suggestion or absence reason available for inspection. | Clears approval and prevents untouched-value eligibility. Blocks a field required by the selected mode until an explicit Accept or valid Edit. | Keep the backend envelope immutable. |
| **Bulk accept displayed values** | User reviews a displayed field/value/source list and explicitly approves the eligible subset. Revalidate the same current draft and each candidate before applying. | `USER_CONFIRMED` for each eligible field | Label each approved value as user-confirmed. | Apply the bulk constraints below. The final mode confirmation remains a separate action. | Preserve each original policy state and record individual user approvals. |
| **Final confirmation** | User chooses one mode and explicitly confirms the eligible current draft under Section 5.4. | Field review states remain as recorded. A separate confirmation result is `COMMITTED` or `FAILED / INVENTORY_PERSISTENCE`. | Show the committed outcome, with an applicable receipt-history entry in the history-saving mode. | Publish exactly the frozen local payload using Section 5.5. | Preserve the backend decisions and separate local approval and commit outcomes. |

Bulk acceptance uses the same source enum and exact candidate ID as Accept, per field. Offer only displayed values that pass the individual acceptance rules and applicable unit/value validation. Exclude invalid values, missing required inventory values, rejected and explicitly unresolved fields, and fields with a true cached unresolved conflict. Pending edits are excluded. A missing optional price can stay absent without bulk approval. If the draft or offered list changes, require the user to review the updated list before applying. Bulk approval neither changes backend readiness/disposition nor records any automatic verification. It does not write inventory.

### 5.3 Sage review safeguards

These rules follow supervisor guideline Section 14 and sections A–B of Tai's approval.

1. **No silent default acceptance of unverified/uncertain suggestions:** Fields in `REVIEW_REQUIRED` or `UNVERIFIED_DRAFT` MUST NOT be pre-marked `"Verified"` or silently committed without explicit user review and final confirmation.
2. **Original OCR and c0 inspection:** Show retained OCR text, `originalB2`, `selectedPreReview`, alternatives, reasons, retailer and price evidence and nullable calibrated probability independently of edits. Show a crop only when the exact submitted frame remains available. Section 5.6 governs retention and deletion.
3. **Never hide price conflicts or unverified status:** `PRICE_CONFLICT` and `NOT_READY` (`UNVERIFIED_DRAFT`) must be surfaced truthfully.
4. **User actions stay distinct from backend verification:** Locally confirmed/edited values carry `actorSource = "USER"` (`USER_CONFIRMED` / `USER_MODIFIED`), never `"AUTO_ACCEPTED"` or backend-verified.

### 5.4 Two explicit confirmation modes

For either mode, require the current validated `RESULT_AVAILABLE` draft for the active request/image and an explicit final tap. Each inventory row needs explicit inclusion. Exclude is a reversible row action that keeps the row and its prior review state in the audit. Show included and excluded items before confirmation. For every field keep draft text, pending/invalid input, the exact accepted source and candidate ID when applicable, approved value and action provenance apart from the immutable backend response. A required value is eligible when explicitly approved via Accept or a valid applied Edit, or when initially untouched with a valid `AUTO_ACCEPTED` value staged for the final user tap. Explicit `UNRESOLVED` or `USER_REJECTED` never qualifies as untouched.

| Mode | Eligibility and published result |
| --- | --- |
| **Confirm inventory only** | Require at least one included inventory item. Each included row needs an eligible valid description, a positive quantity exactly representable at scale zero to three, a confirmed compatible inventory unit, and resolution of any mandatory inventory-field review. Receipt-level fields and monetary fields may remain unreviewed, missing, rejected or unresolved. If receipt information remains incomplete, require an explicit acknowledgement of that fact before the final tap. Preserve those states in any retained review audit. Publish only the included stock changes and confirmation ledger. A partial draft never becomes a complete purchase-history record. |
| **Confirm inventory and save receipt** | Require all inventory-only eligibility plus a complete reviewed history for the represented purchase. Store, purchase date and receipt total require valid eligible values. Every detected purchased row, including every row excluded from inventory, requires valid eligible description, quantity and line total, plus eligible unit price or legitimate optional absence. A missing, conflicted or invalid required history value blocks this mode until individually resolved. If a purchased row is known to be omitted, use inventory-only, recapture or the existing manual receipt flow. Save every detected row with its approved historical quantity and inventory inclusion decision. Publish stock changes for included rows and the full history together. |

For history, allow null unit price when the selected state is untouched `UNIT_PRICE/MISSING` from the receipt, when the user explicitly accepts that missing original or selected record, or when the user explicitly records that no unit price was printed after checking the source. Merely clearing an invalid, rejected or unresolved price is insufficient. Preserve the applicable absence reason. Save the eligible receipt total as reviewed and keep its original backend value in the retained evidence. Inventory exclusions and arithmetic warnings never recalculate either total. Research field completeness, adjudication and metrics are independent of these modes.

### 5.5 Exact inventory and atomic confirmation

Use Tai's reported compatibility basis in `D:\PantryProof\mobile\android` on `feature/tai-android-final`. `ManualInventoryStore.kt`, `PantryUiState.kt` and `LiveReceiptReviewDraft.kt` currently use a versioned local inventory snapshot, validated atomic file replacement and stable inventory row identities. The `live-receipt-` prefix is derived from bound request/image identities, retaining the original row identity. The existing guard also refuses another confirmation with a different selected subset under a committed prefix. Current inventory storage supports whole quantities. The behavior below is the target contract independent of storage technology.

- Parse and store receipt-sourced stock quantities using exact decimal or equivalent fixed-point arithmetic with up to three fractional places. Validate representability and allowed precision for the confirmed unit. Combine quantities only for compatible unit and stock identities. Convert any supported units only if the conversion is explicitly defined and exact. Never round, silently substitute a unit, or merge unlike units. When unsupported, block the affected row and explain how to choose a supported unit, correct the quantity or exclude the row. Migration preserves existing exact quantities and stable identities. Keep legacy unknown units unknown and resolve them before incompatible stock updates. Validate the migrated snapshot before atomic publication and keep the previous version recoverable on failure.
- Allocate one stable confirmation identity for the validated draft, bound to its receipt, request and submitted image, using the existing live-receipt identity scheme. It survives retries and restart. The final tap freezes the mode, included rows, approved values and units, and applicable history. Persist enough pending information to recover an interrupted acknowledgement with the same identity and payload. A new request, replaced image or cancelled draft cannot reuse that identity for a new publication. Tai verifies the exact Kotlin key construction. This guard is for the same confirmation, with no claim of physical-receipt deduplication across distinct uploads.
- Validate and atomically publish all stock updates, applicable purchase-history records and the durable consumed-confirmation ledger. With the snapshot store, publish them in one versioned replacement. Any required private sidecar must already be durable before a snapshot references it. A failed commit leaves the previous publication intact. On retry, first look up the confirmation identity. Return the recorded outcome for a matching committed payload, including when acknowledgement was interrupted. Refuse a different payload or mode under the same consumed identity. Matching committed outcomes do not apply stock again, including after history deletion, inventory edits or restart. A stale uncommitted draft is ineligible for publication.

### 5.6 Sage V5 history and privacy

The app distinguishes the original captured or imported image from the exact prepared crop encoded for submission. Use separate opaque identities. Crop inspection requires the matching submitted image and frame. Historical purchased quantities are the reviewed purchase amounts at confirmation, independent of later stock changes. Keep immutable retained backend evidence, user-approved values and commit state separately. Retained evidence is protected against rewriting and can be deleted.

Store drafts, history and associated private evidence in app-private local storage. Retain processing images only while needed for upload, active review or an explicitly retained evidence view. Delete app-owned temporary copies after cancellation, draft discard, or confirmation when no retained record needs them. Original-image retention is an Android preference proposed to default off until explicitly enabled, subject to final owner confirmation. Leaving it off does not delete an original file owned outside the app. The draft/history experience must tolerate deleted images and OCR evidence, with unavailable evidence labeled accordingly.

Deleting receipt history removes the chosen record and associated private app-owned evidence where applicable, without reversing stock or reopening its confirmation. Retain only the minimal durable confirmation ledger needed for duplicate protection and replay outcome, such as opaque identity, committed marker and an opaque payload fingerprint. Keep receipt images, OCR, product values and purchase details out of that ledger. Use safe deletion and recovery for detached temporary files without breaking references needed by other retained records.

---

## 6. Proposed Shared JSON Fixtures

Proposed synthetic contract fixtures are placed in the canonical presentation-fixture location under a separate `review_v1` directory so the 32 frozen Presentation V1 fixtures remain completely untouched:

- Directory: `tests/fixtures/receipt_presentation_v1/review_v1/`
- Index manifest: `tests/fixtures/receipt_presentation_v1/review_v1/manifest.json`
- Usage guide: `tests/fixtures/receipt_presentation_v1/review_v1/README.md`
- Fixture files: `tests/fixtures/receipt_presentation_v1/review_v1/fixtures/*.json`

All fixtures use the shared test container (`fixtureStatus: "PROPOSED_NOT_YET_APPROVED — SYNTHETIC_ONLY"`, `scenario`, `expectedResult`, `expectedPath`, `consumerContext`, `envelope`). Pass the exact original UTF-8 object span of `envelope` to the decoder. V1 objects have valid structure. Request/image mismatch cases deliberately supply the wrong external association. The manifest pins hashes and rejection paths and specifies deterministic raw byte-limit variants without storing megabytes of whitespace. The fixture README defines their construction. These are synthetic verification inputs.

| Fixture file | Scenario covered | Field roles exercised | Expected validation result |
| --- | --- | --- | --- |
| `01-policy-verified-correction.json` | 1. Policy-verified correction + 2. Retained original value | All 7 roles (`STORE_NAME`, `PURCHASE_DATE`, `RECEIPT_TOTAL`, `ITEM_DESCRIPTION`, `QUANTITY`, `UNIT_PRICE`, `LINE_TOTAL`) | `ACCEPT` |
| `02-retained-original-and-missing-price.json` | 2. Retained original value + 5. Missing price evidence (`PRICE_UNAVAILABLE`) | All 7 roles, including optional `UNIT_PRICE/MISSING` | `ACCEPT` |
| `03-review-required-with-alternatives.json` | 3. Review-required value with alternatives + source spans + retailer/price evidence | All 7 roles | `ACCEPT` |
| `04-unverified-development-draft.json` | 4. Unverified development draft (`NOT_READY`, `UNVERIFIED_DRAFT`, null probability, advisory recommendation) | All 7 roles | `ACCEPT` |
| `05-conflicting-and-inconclusive-price.json` | 6. Conflicting (`PRICE_CONFLICT` + `REJECTED_PRICE_ONLY`) and inconclusive (`PRICE_INCONCLUSIVE`) price evidence | All 7 roles | `ACCEPT` |
| `06-unavailable-calibrated-probability.json` | 7. Unavailable calibrated probability (`probabilityAvailable: false`, `calibratedProbability: null`, forced `REVIEW_REQUIRED` on `c0`) | All 7 roles | `ACCEPT` |
| `07-source-evidence-fallback.json` | 8. Source-evidence fallback (`SOURCE_EVIDENCE_INSUFFICIENT`, `FALLBACK_NO_UPDATE`) | N/A (`fields: []`) | `ACCEPT` |
| `08-technical-failure.json` | 9. Pre-resolution technical failure (`PROCESSING_FAILED`, `FAILED / PRE_RESOLUTION`, `PROPOSED_METHOD_FAILURE`) | N/A (`fields: []`) | `ACCEPT` |
| `09-invalid-candidate-reference.json` | 10. Selected candidate ID does not resolve within its field | All 7 roles (defect on `ITEM_DESCRIPTION`) | `REJECT_INVALID_REVIEW_REFERENCE` |
| `10-invalid-field-reference.json` | 10. Invalid field reference (`review.fields[0].fieldId` mismatches `presentation.receipt.receiptFields[0].fieldId`) | All 7 roles (defect on `STORE_NAME`) | `REJECT_INVALID_REVIEW_REFERENCE` |
| `11-unsupported-schema-version.json` | 11. Unsupported schema version (`schemaVersion: "999"`) | All 7 roles in the embedded V1, wrapper rejected before mapping | `REJECT_UNSUPPORTED_SCHEMA_VERSION` |
| `12-invalid-probability-state.json` | 12. Non-null probability with `probabilityAvailable: false` | All 7 roles (defect on `STORE_NAME`) | `REJECT_REVIEW_STATE` |
| `13-exact-weighted-quantity.json` | Exact `0.750` with a linked literal unit and independently scoped price/pantry evidence | `QUANTITY` and its source association | `ACCEPT` |
| `14-quantity-unit-unavailable.json` | Exact `0.750` with no unit in the linked quantity literal. Comparator and pantry basis do not supply one. | `QUANTITY` and its source association | `ACCEPT` |
| `15-request-id-mismatch.json` | Expected request ID differs from embedded V1 | Request association | `REJECT_REQUEST_ID_MISMATCH` |
| `16-image-id-mismatch.json` | Expected image ID differs from embedded V1 | Image association | `REJECT_IMAGE_ID_MISMATCH` |
| `17-coordinate-frame-mismatch.json` | Valid OCR coordinates in a frame whose width differs from the submitted image | Image dimensions | `REJECT_INVALID_REVIEW_REFERENCE` |

---

## 7. Implementation Ownership and Compatibility Obligations

| Responsibility | Owner | Concrete Deliverables & Obligations (Post Joint Approval) |
| --- | --- | --- |
| Python review-response producer & evidence mapper | **Leng** | Project `RetainedLocalImageAttemptV0` (OCR tokens/polygons/confidences, `B2ExtractionResult`, `ReceiptCorrectionResult`, `ProposedReceiptResearchResult`, `pantry_matches`) into `receipt-review` v1 JSON bytes when `X-Response-Schema: receipt-review-v1` is selected; keep default strict V1 unchanged. |
| Python review-response conformance validator | **Leng** | Add strict decoder/validator for `receipt-review` v1 (reusing `validate_presentation_v1_object` on `presentation`, checking all member sets, cross-references, privacy rules, and null-probability invariants) without modifying Presentation V1 validation. |
| HTTP header version negotiation | **Leng** | In `real_receipt_http_service_v1.py`, support `X-Response-Schema` (bare Presentation V1 by default, review on explicit selection, `400` malformed, `406` unsupported) and enforce both exact byte limits. Test negotiation and status precedence at the transport boundary. |
| Shared fixture suite parity | **Leng & Tai** | Maintain one canonical physical fixture set under `tests/fixtures/receipt_presentation_v1/review_v1/`; both Python and Kotlin test suites verify exact raw-byte SHA-256 hashes and identical `ACCEPT`/`REJECT_*` codes. |
| Android decoder & validator | **Tai** | Extend the existing API-26-safe strict JSON decoding approach for `receipt-review` v1 in Kotlin, failing closed on version, structure, privacy and cross-reference violations. Keep Presentation V1 decoding and validation intact. |
| Sage V5 review, confirmation, inventory and history | **Tai** | Keep existing capture and navigation and implement the seven-field review UI, five-state and bulk interactions, both confirmation modes, exact decimal inventory with lossless migration, ledger and atomic persistence behavior, history, private evidence and optional image retention. Verify the reported Kotlin identity and storage mapping in focused implementation checks. |

Android verifies untouched vs. explicitly unresolved and rejected fields, candidate-specific and bulk approval, both confirmation modes including incomplete acknowledgement and excluded rows, exact weighted/unit persistence and legacy migration, interrupted acknowledgement replay and duplicate prevention after history deletion. These are Kotlin-local behavior tests. They add no UI or persistence state to the wire. The jointly coordinated runtime verification is in [prototype_runtime.md](prototype_runtime.md).
