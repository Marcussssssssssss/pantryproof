# Receipt Presentation V1 — Fixture Expansion Proposal

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

**Package ID:** `M3D-0R-PROPOSAL-2026-11-04`  
**Status:** `PROPOSED_FIXTURES_NOT_CREATED`

This file identifies exact successor updates and additional fixture scenarios.
It does not modify the original nine fixture bytes or their expected results.
The S-06 expectations are shared-owner agreed; no successor fixture set is
frozen or authorized until full M3D contract approval.

## 1. Successor fixture-set rules

After joint approval, create a new directory such as
`fixtures-proposed-v1/`; do not overwrite `fixtures-draft/`.

The successor wrapper retains:

```json
{
  "fixtureStatus": "DRAFT_NOT_APPROVED — SYNTHETIC_ONLY",
  "scenario": "scenario-name",
  "expectedResult": "ACCEPT_OR_SPECIFIC_REJECTION",
  "consumerContext": null,
  "envelope": {}
}
```

`consumerContext` is fixture-only metadata. It is null except where request,
image, or test/live-mode policy is under test. Existing fixture wrappers remain
valid without that member; their harness may infer matching expected IDs and
`FIXTURE` mode.

Each negative fixture should contain exactly one intended defect unless a JSON
syntax defect inherently prevents semantic parsing. This keeps cross-runtime
error attribution deterministic.

## 2. Required successor copies of the original nine

Copy all nine originals into the future successor set and apply only the jointly
approved schema changes. Preserve every current `expectedResult`.

| Original | Proposed successor-only update |
|---|---|
| 01 complete extracted receipt | Add `receipt.currencyCode: "MYR"`; change date `originalAutomaticValue` to `2026-10-15` so it equals canonical presentation date |
| 02 missing optional unit price | Add `receipt.currencyCode: "MYR"` |
| 03 missing required store | Add `receipt.currencyCode: "MYR"` |
| 04 unresolved date | Add `receipt.currencyCode: "MYR"` |
| 05 decimal quantity | Add `receipt.currencyCode: "MYR"` |
| 06 processing unavailable | No content change proposed |
| 07 processing failure | No content change proposed |
| 08 unsupported schema version | No content change proposed; version rejection remains first |
| 09 malformed status/value | Add `receipt.currencyCode: "MYR"`; preserve the existing contradictory unit-price state and rejection label |

## 3. Proposed positive additions

| No. / proposed filename | Expected result | Exact purpose |
|---|---|---|
| `10-canonical-money-normalization.proposed.json` | `ACCEPT` | `UNIT_PRICE` original `MYR 1,234.50`, canonical `1234.50`, currency `MYR`; proves permitted lexical normalization only |
| `11-zero-money.proposed.json` | `ACCEPT` | Extracted unit price `0.00`; proves non-negative rather than strictly positive money |
| `12-quantity-scale-three-boundary.proposed.json` | `ACCEPT` | Quantity `0.001`; proves positive maximum scale three and no integer conversion |
| `13-missing-with-token-reference.proposed.json` | `ACCEPT` | `MISSING`, null values/confidence, nonblank reason, and one valid token reference |
| `14-unresolved-with-empty-token-list.proposed.json` | `ACCEPT` | `UNRESOLVED` with null values/confidence, nonblank reason, and no token reference |
| `15-result-available-extraction-failed.proposed.json` | `ACCEPT` | Sufficient gate, available receipt, `extractionStatus: FAILED`, all receipt fields missing, zero rows; proves status preservation and outer/status separation |
| `16-source-evidence-insufficient.proposed.json` | `ACCEPT` | `SOURCE_EVIDENCE_INSUFFICIENT` with genuine `OCR_COMPLETED` evidence, actual source-bound insufficient gate with nonempty reasons, and null failure/extraction/receipt |
| `17-valid-content-digest.proposed.json` | `ACCEPT` | Exactly 64 lowercase hexadecimal SHA-256 characters |
| `18-local-image-source-shape.proposed.json` | `ACCEPT` | Synthetic fixture wrapper around envelope `source.type: LOCAL_IMAGE`, opaque reference, no URI/path |
| `19-two-row-order-preservation.proposed.json` | `ACCEPT` | Two row IDs deliberately not in lexical order; consumer preserves array order |
| `20-finite-native-confidence-outside-unit-interval.proposed.json` | `ACCEPT` | Extracted field with finite `nativeConfidence: -1.5`; proves no invented calibrated 0-1 range |
| `21-open-producer-id.proposed.json` | `ACCEPT` | Valid non-B1/B2/B3 opaque producer ID with required version |
| `75-source-evidence-insufficient-partial.proposed.json` | `ACCEPT` | Genuine `OCR_PARTIAL` evidence, actual source-bound insufficient gate with nonempty reasons, preserved status/tokens/provenance, and null failure/extraction/receipt |
| `76-source-evidence-insufficient-received.proposed.json` | `ACCEPT` | Genuine `RECEIVED` evidence with the same actual insufficient-gate and null-output conditions; no inferred OCR success |
| `77-source-evidence-insufficient-ocr-failed.proposed.json` | `ACCEPT` | Genuine `OCR_FAILED` evidence with the same actual insufficient-gate and null-output conditions; no fabricated evidence or OCR-success claim |

## 4. Proposed negative additions and resolved outcome profiles

### 4.1 Value and canonicalization rules

| No. / proposed filename | Expected result | Single defect |
|---|---|---|
| `22-unit-price-one-decimal.proposed.json` | `REJECT_INVALID_MONEY` | Unit-price presentation value `6.5` |
| `23-unit-price-three-decimals.proposed.json` | `REJECT_INVALID_MONEY` | Unit-price presentation value `6.500`; proves no rounding |
| `24-money-prefix-in-presentation.proposed.json` | `REJECT_INVALID_MONEY` | Canonical presentation value still contains `RM` |
| `25-dollar-original-for-myr.proposed.json` | `REJECT_CURRENCY_MISMATCH` | Original `$6.50` with receipt currency `MYR` |
| `26-missing-currency-code.proposed.json` | `REJECT_CURRENCY_METADATA` | Available receipt omits `currencyCode` |
| `27-unsupported-currency-code.proposed.json` | `REJECT_CURRENCY_METADATA` | Available receipt uses non-`MYR` currency in V1 |
| `28-quantity-zero.proposed.json` | `REJECT_INVALID_QUANTITY` | Canonical quantity `0` |
| `29-quantity-scale-four.proposed.json` | `REJECT_INVALID_QUANTITY` | Canonical quantity `0.0001` |
| `30-quantity-exponent.proposed.json` | `REJECT_INVALID_QUANTITY` | Canonical quantity `1e1` |
| `31-quantity-negative.proposed.json` | `REJECT_INVALID_QUANTITY` | Canonical quantity `-1` |
| `32-quantity-leading-zero.proposed.json` | `REJECT_INVALID_QUANTITY` | Canonical quantity `01` |
| `33-invalid-gregorian-date.proposed.json` | `REJECT_INVALID_DATE` | Canonical date `2026-02-30` |
| `34-noncanonical-extracted-date.proposed.json` | `REJECT_VALUE_RELATIONSHIP` | Extracted original `15/10/2026` with ISO presentation date |
| `35-text-presentation-value-changed.proposed.json` | `REJECT_VALUE_RELATIONSHIP` | Item/store text differs between original and presentation values |

### 4.2 JSON, version, and member rules

| No. / proposed filename | Expected result | Single defect |
|---|---|---|
| `36-unknown-envelope-member.proposed.json` | `REJECT_UNKNOWN_MEMBER` | One undeclared top-level envelope member |
| `37-unknown-field-member.proposed.json` | `REJECT_UNKNOWN_MEMBER` | One undeclared field member, such as external price evidence |
| `38-duplicate-json-key.proposed.json` | `REJECT_DUPLICATE_JSON_KEY` | Raw bytes contain duplicate `schemaVersion` keys |
| `39-unsupported-source-contract-version.proposed.json` | `REJECT_UNSUPPORTED_CONTRACT_VERSION` | `sourceContractVersion` is not `0` |
| `40-missing-required-nullable-member.proposed.json` | `REJECT_MISSING_MEMBER` | Omit `outcome.failure` rather than include explicit null |
| `41-unknown-enum-value.proposed.json` | `REJECT_UNKNOWN_ENUM` | Unknown field status or outcome value |
| `42-nonfinite-confidence-overflow.proposed.json` | `REJECT_INVALID_CONFIDENCE` | Valid JSON number `1e400` becomes non-finite binary64 |
| `43-nonstandard-nan-token.proposed.json` | `REJECT_INVALID_JSON` | Raw `NaN` token, which strict JSON must reject |

### 4.3 Identity, ordering, and provenance rules

| No. / proposed filename | Expected result | Single defect |
|---|---|---|
| `44-request-context-mismatch.proposed.json` | `REJECT_REQUEST_ID_MISMATCH` | Wrapper expected request differs from envelope request |
| `45-image-context-mismatch.proposed.json` | `REJECT_IMAGE_ID_MISMATCH` | Wrapper expected image differs from envelope image |
| `46-malformed-protocol-id.proposed.json` | `REJECT_INVALID_ID` | Required ID contains whitespace/slash or begins outside the grammar |
| `47-unsafe-content-uri-source-reference.proposed.json` | `REJECT_UNSAFE_PROVENANCE` | `sourceReference` contains `content://...` |
| `48-unsafe-windows-path-source-reference.proposed.json` | `REJECT_UNSAFE_PROVENANCE` | `sourceReference` contains a drive/path |
| `49-malformed-content-digest.proposed.json` | `REJECT_INVALID_DIGEST` | Digest length or character set is invalid |
| `50-uppercase-content-digest.proposed.json` | `REJECT_INVALID_DIGEST` | Digest contains uppercase hexadecimal |
| `51-duplicate-field-id.proposed.json` | `REJECT_DUPLICATE_FIELD_ID` | Same field ID occurs twice receipt-wide |
| `52-duplicate-row-id.proposed.json` | `REJECT_DUPLICATE_ROW_ID` | Same row ID occurs twice |
| `53-missing-required-role.proposed.json` | `REJECT_ROLE_SET` | One required receipt/item role is absent |
| `54-duplicate-required-role.proposed.json` | `REJECT_ROLE_SET` | One role appears twice |
| `55-unknown-field-role.proposed.json` | `REJECT_UNKNOWN_ROLE` | Field role is outside the seven-role enum |
| `56-out-of-order-item-role.proposed.json` | `REJECT_ROLE_ORDER` | Valid item roles appear in a different array order |

### 4.4 Token and field-state integrity

| No. / proposed filename | Expected result | Single defect |
|---|---|---|
| `57-unknown-token-reference.proposed.json` | `REJECT_UNKNOWN_TOKEN_REFERENCE` | Field reference is absent from projected token registry |
| `58-duplicate-token-id.proposed.json` | `REJECT_DUPLICATE_TOKEN_ID` | Registry contains duplicate token ID |
| `59-duplicate-token-reference.proposed.json` | `REJECT_DUPLICATE_TOKEN_REFERENCE` | One field repeats a token reference |
| `60-extracted-without-token-reference.proposed.json` | `REJECT_TOKEN_INTEGRITY` | Extracted field has empty token list |
| `61-blank-absence-reason.proposed.json` | `REJECT_CONTRADICTORY_FIELD_STATE` | Missing/unresolved reason contains only defined ASCII whitespace |
| `62-missing-field-with-confidence.proposed.json` | `REJECT_CONTRADICTORY_FIELD_STATE` | Missing field carries native confidence |
| `63-unresolved-field-with-value.proposed.json` | `REJECT_CONTRADICTORY_FIELD_STATE` | Unresolved field carries either automatic value |

### 4.5 Outcome, gate, and producer consistency

| No. / proposed filename | Expected result | Single defect |
|---|---|---|
| `64-result-with-null-gate.proposed.json` | `REJECT_GATE_OUTCOME_MISMATCH` | Available result has no gate |
| `65-result-with-insufficient-gate.proposed.json` | `REJECT_GATE_OUTCOME_MISMATCH` | Available result has insufficient gate |
| `66-result-with-failure-object.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Available result also carries failure |
| `68-unavailable-with-evidence.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Capability-unavailable outcome carries evidence |
| `69-failure-with-receipt.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Technical failure carries receipt/extraction |
| `70-insufficient-gate-empty-reasons.proposed.json` | `REJECT_GATE_STATE` | Insufficient gate has no reason |
| `71-insufficient-outcome-with-failure.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | An attempted V1 insufficient-evidence envelope carries a technical failure; this rejection does not define handling for a later projection exception |
| `72-insufficient-outcome-with-sufficient-gate.proposed.json` | `REJECT_GATE_OUTCOME_MISMATCH` | Insufficient-evidence outcome has sufficient decision |
| `73-missing-producer-version.proposed.json` | `REJECT_PRODUCER_METADATA` | Available extraction omits/blank producer version |
| `74-live-mode-synthetic-source.proposed.json` | `REJECT_SOURCE_MODE_MISMATCH` | Wrapper mode is live while envelope source is `SYNTHETIC_FIXTURE` |
| `78-insufficient-outcome-without-gate.proposed.json` | `REJECT_GATE_OUTCOME_MISMATCH` | Insufficient-evidence outcome has no recorded gate |
| `79-insufficient-outcome-with-extraction.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Insufficient-evidence outcome fabricates automatic extraction metadata |
| `80-insufficient-outcome-with-receipt.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Insufficient-evidence outcome fabricates receipt content |
| `81-result-without-automatic-extraction.proposed.json` | `REJECT_OUTCOME_STATE_MISMATCH` | Available result omits required automatic extraction metadata |

### 4.6 Resolved available-result evidence profiles

Leng's dated R2 resolution makes these proposed accepts, but only when each is
constructed from a genuine structurally valid synthetic Contract V0 upstream
object meeting every available-result condition:

| No. / proposed filename | Expected result | Required construction |
|---|---|---|
| `67-result-with-ocr-failed-evidence.proposed.json` | `ACCEPT` | Genuine `ReceiptOutput` and evidence, actual source-bound `SUFFICIENT` gate, required extraction metadata/receipt, matching request/image identities, and preserved extraction status/provenance; no inferred OCR success |
| `67a-result-with-received-evidence.proposed.json` | `ACCEPT` | Same full conditions with genuine `RECEIVED` evidence; no fabricated output or inferred OCR success |

Do not simply relabel an invalid fixture. Their future bytes must be derived
from structurally valid synthetic upstream objects after full M3D contract
approval and separate fixture-construction authorization.

### 4.7 S-06 stage-specific reconciliation

The separate S-06 clarification proposes seven accepted technical-failure
fixtures and 25 rejected technical-failure fixtures. Leng's recorded backend
conditions support those stage-specific expectations, including the additional
rejections for OCR failure with `RECEIVED`/`OCR_PARTIAL`, and downstream
technical failures with `RECEIVED`/`OCR_FAILED`. They remain contract proposals
whose S-06 expectations are `S06_SHARED_OWNER_DESIGN_AGREED`; their bytes still
require full M3D contract approval and separate construction authorization.

The rejection proposals carrying a recorded `INSUFFICIENT` gate reject only an
attempted contradictory V1 JSON envelope. They do not define the deferred
backend lifecycle after envelope construction itself fails; that lifecycle is
outside V1 JSON conformance.

Required rejection coverage is explicitly mapped as follows:

| Required rejection category | Proposed fixture coverage |
|---|---|
| Missing recorded gate | 64 for available output; 78 for insufficient evidence |
| Wrong gate decision | 65 and 72 |
| Empty insufficiency reasons | 70 |
| Contradictory technical failure | 71 |
| Fabricated extraction or receipt | 79 and 80 |
| Missing required available-result metadata | 64, 73, and 81 |
| Incorrect request/image binding | 44 and 45 |

### 4.8 Deferred non-JSON lifecycle scenario

`lifecycle-s06-insufficient-gate-then-projection-exception` records:

1. a genuine `INSUFFICIENT` gate was durably recorded;
2. later backend presentation/projection failed before a successful envelope
   existed; and
3. no successful `SOURCE_EVIDENCE_INSUFFICIENT` response was produced.

Its status is `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`. It is a
documentation/test-plan scenario, not a JSON fixture; it has no V1
`expectedResult`, must not contain a fabricated envelope, and must not be mapped
to `SOURCE_GATE`, current `PRESENTATION_ADAPTER`, `PROCESSING_UNAVAILABLE`, or a
fifth terminal outcome.

### 4.9 Proposed scenario totals

The numbered JSON additions, including `67a`, contain 17 proposed `ACCEPT` and
56 proposed `REJECT` cases: 73 proposed JSON additions total, with no pending
JSON expectation. Separately, the S-06 clarification contains seven
proposed `ACCEPT` and 25 proposed `REJECT` stage-specific JSON cases. The one
deferred Case B lifecycle scenario is non-JSON. These totals exclude the nine
original successor copies, whose existing bytes and expected results remain
unchanged.

## 5. Priority for the first synthetic conformance milestone

Before validator implementation, the successor copies plus fixtures 10, 12-20,
22-24, 26, 28-30, 33-46, 51-70, `67a`, and 73-81 are recommended as the
blocking core after full M3D contract approval.
Fixtures 11, 21, 25, 27, 31, 32, 47-50, and 71-72 are additional boundary
coverage that should be created before the contract is called complete, but they
need not block a first parser skeleton once the related rule is explicitly
recorded.

The agreed technical-failure expectations in the S-06 clarification should join
the same core only after full M3D contract approval. Fixtures 67 and 67a are now
proposed accepts subject to their full construction conditions. The Case B
lifecycle remains deferred and requires a later transport/error-handling design,
not a fabricated conformance fixture.

No fixture authoring or validator implementation is authorized by this proposal.

## Classification

`DRAFT_NOT_APPROVED — SYNTHETIC_ONLY`

`S06_SHARED_OWNER_DESIGN_AGREED`

`M3D_FULL_CONTRACT_APPROVAL_PENDING`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
