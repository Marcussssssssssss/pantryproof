# PantryProof M3E-1P — Synthetic Conformance Implementation Preflight and Scope Lock

`PROPOSAL — PENDING_TAI_AND_LENG_SCOPE_APPROVAL`

**Scope candidate:** `M3E-1P-SCOPE-CANDIDATE-2026-11-05`  
**Approved design:** `M3D-1-APPROVAL-CANDIDATE-2026-11-04`  
**Direction decision:** `LENG_M3E_1_DIRECTION_APPROVED`  
**Repository:** `D:/PantryProof`  
**Branch:** `feature/tai-android-ui`  
**HEAD inspected:** `656c9824becdaf392f59ca510df392d82e4b7d0c`  
**Prepared:** 2026-11-05 (Asia/Kuala_Lumpur)

## 1. Purpose, authority, and result

This document is an implementation-ready scope proposal for a future
synthetic-only M3E-1 conformance milestone. It fixes the proposed file allowlist,
canonical fixture location, initial fixture set, validation responsibilities,
verification commands, and independent-review boundary.

It does **not** authorize or implement Kotlin/Python code, fixture bytes, OCR,
source-gate orchestration, runtime integration, persistence, scoring,
calibration, evaluation, or real-receipt processing. The two copy-ready owner
statements in Section 11 are templates only and are not signed approvals.

## 2. Read-only Git preflight

| Check | Result |
|---|---|
| Repository root | `D:/PantryProof` |
| Origin | `https://github.com/Marcussssssssssss/pantryproof` |
| Required branch | `feature/tai-android-ui` — `MATCH` |
| Expected HEAD | `656c9824becdaf392f59ca510df392d82e4b7d0c` — `MATCH` |
| HEAD subject | `docs(android): record jointly approved M3D receipt presentation contract` |
| Index | No staged changes |
| Tracked worktree | No tracked changes |
| Untracked content | Existing project-local skills, UI design document, Android verification artifacts, and `skills-lock.json`; preserved |
| Primary worktree | `D:/PantryProof`, required branch |
| Secondary worktree | `D:/PantryProof-android-ui`, detached at `63317df1fbed042cb035db54b1ac7a604f7f3555`; untouched |

The M3D checkpoint exists at HEAD and contains the authoritative design inputs,
closure record, owner evidence, and original nine draft fixtures. No fetch,
pull, branch change, staging, commit, push, merge, rebase, reset, stash, clean,
or worktree mutation was performed.

## 3. Approved contract-manifest verification

All five calculated SHA-256 values match the M3D-1 manifest exactly.

| Authoritative file | Recorded and calculated SHA-256 | Result |
|---|---|---|
| `mobile/android/verification/m3d/receipt-presentation-v1-draft.md` | `1E56F3C82716E889E46DEEE898233C2C143FDD6122F715A1C8E32EADCCCB01E5` | `MATCH` |
| `mobile/android/verification/m3d/shared-decision-register.md` | `5C3284D54C604CC71293DDC4FD3EB87E2B8099A38DF4CA9A915403BB667DBB16` | `MATCH` |
| `mobile/android/verification/m3d/contract-closure-proposal.md` | `A3FD591589D9433EBA4C2F64743E0353E19978915AAE9BF1ACFE6F0E4B9F8EEC` | `MATCH` |
| `mobile/android/verification/m3d/fixture-expansion-proposal.md` | `D7E40604AE3DC67FE291414AC817739F2B05DA9CE334C1D7379536FB1CA71293` | `MATCH` |
| `mobile/android/verification/m3d/s06-failure-stage-clarification.md` | `003D4348924EE5A5D54B1EE9354EA36DFC4DDEE29FF46FFB3DB6966BFE904269` | `MATCH` |

The closure remains `M3D_CONTRACT_DESIGN_JOINTLY_APPROVED`. The post-insufficient
gate presentation exception remains `DEFERRED — OUTSIDE V1 JSON CONFORMANCE`.

## 4. Existing architecture and isolation boundary

### 4.1 Android

- The app remains Kotlin/native Android Views with `minSdk = 26`,
  `compileSdk/targetSdk = 36`, and JVM 17.
- `ReceiptModels.kt` represents completed UI data and uses integer receipt
  quantities. It cannot represent V1 incomplete fields, decimal quantities,
  tokens, provenance, processing states, or immutable original values.
- `ReceiptValidator.kt` validates editable UI strings and produces the existing
  UI `Receipt`; it is not the V1 semantic validator.
- `ReceiptPresentationSource` and `MockReceiptPresentationSource` remain the
  current synthetic UI seam. M3E-1 must not implement or activate a new source,
  alter `MainActivity`, or map decoded V1 data into the UI.
- The new package is isolated at
  `com.pantryproof.prototype.contract.v1` and contains no Android framework,
  navigation, inventory, review, OCR, evaluation, or proposed-method types.

### 4.2 Python

- `pipeline/contracts.py` is protected Contract V0 and remains read-only. It
  already supplies immutable source evidence, gates, tokens, fields, rows, and
  `ReceiptOutput` invariants.
- A valid available-result test projection may consume a genuine synthetic
  `ReceiptOutput`. An insufficient-evidence test projection consumes genuine
  `ReceiptSourceEvidence` directly; it must not manufacture `ReceiptOutput`.
- The strict V1 JSON validator is a new isolated package and does not activate
  OCR, B1/B2/B3, source-gate orchestration, proposed-method code, evaluation, or
  persistence.
- The handcrafted Contract V0 projection boundary is test support only. It is
  never a production gateway and must redact raw `SourceProvenance` references.

## 5. Exact implementation file allowlist

### 5.1 Tai-owned Android allowlist

| Repository-relative path | State | Purpose | Protected-contract risk |
|---|---|---|---|
| `mobile/android/app/src/main/java/com/pantryproof/prototype/contract/v1/ReceiptPresentationV1Models.kt` | `NEW` | Immutable envelope, source/provenance, outcome/failure, evidence/gate, extraction/producer, receipt/row/field DTOs, enums, caller context, and deterministic issue/result types | Low; presentation-only types must not replace existing UI models |
| `mobile/android/app/src/main/java/com/pantryproof/prototype/contract/v1/ReceiptPresentationV1Decoder.kt` | `NEW` | Strict raw UTF-8 decoding; duplicate-key, invalid JSON, unknown member/enum, missing-member, type, trailing-content, and unsupported-version rejection | Medium; parser configuration and validation precedence must match the frozen contract |
| `mobile/android/app/src/main/java/com/pantryproof/prototype/contract/v1/ReceiptPresentationV1Validator.kt` | `NEW` | Semantic validation for correlation, IDs/privacy, ordering, field states/tokens, money/quantity/date grammar, four outcomes, S-06 stage matrix, and extraction-status preservation | Medium; must not reinterpret Contract V0 or infer correctness |
| `mobile/android/app/src/test/java/com/pantryproof/prototype/contract/v1/ReceiptPresentationV1DecoderTest.kt` | `NEW` | Lexical/structural unit tests, including strict UTF-8, duplicate keys, unknown members, required nulls, unsupported versions, and trailing input | Low; synthetic only |
| `mobile/android/app/src/test/java/com/pantryproof/prototype/contract/v1/ReceiptPresentationV1ValidatorTest.kt` | `NEW` | Language-local semantic boundary tests for all approved rules not all represented in the initial shared fixture subset | Low; synthetic only |
| `mobile/android/app/src/test/java/com/pantryproof/prototype/contract/v1/ReceiptPresentationV1SharedFixtureConformanceTest.kt` | `NEW` | Locate and hash canonical fixture-wrapper bytes; strictly read the test-only wrapper/context; pass only its nested envelope token stream to production decoding/validation; assert deterministic expected results | Low; test-only repository discovery and wrapper handling, no copied fixtures or wrapper support in production |
| `mobile/android/app/build.gradle.kts` | `EXISTING — SEPARATE EXPLICIT APPROVAL REQUIRED` | Add only `implementation("com.fasterxml.jackson.core:jackson-core:2.21.8")`; no plugin/toolchain/source-set change | Medium; only existing application file proposed, changes dependency graph |

No other Android file is allowlisted. In particular, M3E-1 excludes
`MainActivity.kt`, `ReceiptModels.kt`, `ReceiptPresentationSource.kt`,
`MockReceiptPresentationSource.kt`, `ReceiptValidator.kt`, `PantryUiState.kt`,
the manifest, resources, navigation, and instrumentation tests.

The Jackson choice is narrowly justified: `jackson-core` provides a streaming
parser and explicit `StreamReadFeature.STRICT_DUPLICATE_DETECTION`, while the
2.21 line is LTS and supports Android SDK 26. Do not add `jackson-databind`,
Jackson Kotlin modules, reflection, generated serializers, or another JSON
library. Official references:

- `https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.21`
- `https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/2.21.8/com/fasterxml/jackson/core/StreamReadFeature.html`

### 5.2 Leng-owned Python allowlist

| Repository-relative path | State | Purpose | Protected-contract risk |
|---|---|---|---|
| `pipeline/presentation_v1/__init__.py` | `NEW` | Narrow public export surface for V1 decoding/validation only | Low; must not export runtime OCR/integration functions |
| `pipeline/presentation_v1/conformance.py` | `NEW` | Immutable validated-envelope types plus strict bytes-to-JSON decoding and full deterministic semantic validation | Medium; no protected-contract mutation, producer selection, scoring, correction, or runtime activation |
| `tests/presentation_v1_projection_support.py` | `NEW` | Test-only handcrafted projection from genuine synthetic Contract V0 evidence/output with identity/token checks and provenance redaction | Medium; must never become a production gateway |
| `tests/test_presentation_v1_conformance.py` | `NEW` | Manifest-driven validation of the same canonical fixture-wrapper bytes; strict test-only wrapper/context handling passes only the nested envelope object to production conformance validation | Low; synthetic only; wrapper support must not enter the production API |
| `tests/test_presentation_v1_projection.py` | `NEW` | Synthetic Contract V0 projection preservation/integrity tests, including all source statuses and `extractionStatus: FAILED` | Low; must not invoke B1/B2/B3, OCR, proposed, or evaluation code |

No existing Python file is allowlisted for modification. In particular,
`pipeline/contracts.py`, `pipeline/ocr_adapter.py`, `pipeline/__init__.py`,
`pipeline/baseline_b1.py`, `pipeline/layout_b2.py`, `pipeline/baseline_b3.py`,
`pipeline/proposed/**`, existing tests, and evaluation code remain read-only or
protected. Python uses only the standard library (`json`, `decimal`, `datetime`,
`re`, `math`, `dataclasses`, `hashlib`, `pathlib`, and `unittest`).

### 5.3 Shared allowlist

| Repository-relative path | State | Purpose | Protected-contract risk |
|---|---|---|---|
| `tests/fixtures/receipt_presentation_v1/v1/README.md` | `NEW` | Frozen-fixture usage, raw-byte hashing, provenance, and cross-language instructions | Low; must state synthetic-only and non-runtime scope |
| `tests/fixtures/receipt_presentation_v1/v1/manifest.json` | `NEW` | Exact fixture path, expected result, decision IDs, SHA-256, byte length, and source classification | Medium; becomes the cross-language conformance oracle only after separate owner authorization and review |
| The 32 JSON files in Section 6 | `NEW` | One canonical physical set consumed directly by Kotlin and Python | Medium; bytes must be independently reviewed against approved design and synthetic Contract V0 provenance where required |

No Android copy of the fixture tree is permitted. The Kotlin test locates
`tests/fixtures/receipt_presentation_v1/v1/manifest.json` by walking upward from
its test working directory and fails if the canonical repository root cannot be
found. Python reads the same path with `pathlib.Path`.

The canonical JSON files are **test fixture wrappers**, using the approved
`fixtureStatus`, `scenario`, `expectedResult`, optional `consumerContext`, and
`envelope` members. They are not runtime envelope roots. For the unchanged
historical wrappers, absent `consumerContext` means matching request/image IDs
and fixture mode, exactly as defined by the approved fixture proposal. Each
language's test-only harness must strictly parse the wrapper, reject duplicate
or unknown wrapper members, confirm its `expectedResult` agrees with the
manifest, apply its consumer context, and feed only the nested `envelope` token
stream/object into production conformance decoding/validation. Production code
must reject wrapper members at an envelope root and must not gain a fixture-mode
wrapper API. The wrapper parse must remain duplicate-aware throughout the nested
envelope and must never use a forgiving parse/reserialize step.

## 6. Initial canonical fixture allowlist and expected outcomes

This is the smallest recommended implementation-complete initial suite: **32
JSON fixtures, 17 ACCEPT and 15 REJECT**. It covers the requested baseline, all
four source-processing statuses for both available and insufficient-evidence
outcomes, each technical-failure stage, and one prohibited evidence profile per
technical-failure stage. The rest of the approved expansion remains deferred to
a later shared-fixture milestone and must still receive language-local unit
coverage where applicable.

All paths below are under
`tests/fixtures/receipt_presentation_v1/v1/fixtures/`.

| Fixture path | Expected result | Primary decision IDs | Byte source / SHA-256 action |
|---|---|---|---|
| `01-complete-extracted-receipt.json` | `ACCEPT` | T-01,T-04; L-01–L-07; S-01–S-09,S-11 | `HISTORICAL_SUCCESSOR`: add `currencyCode: MYR`; make original date equal canonical ISO date; calculate new raw-byte hash |
| `02-missing-optional-unit-price.json` | `ACCEPT` | T-02,T-04,T-05; L-01,L-02,L-04–L-06; S-01–S-03,S-05,S-06,S-08–S-11 | `HISTORICAL_SUCCESSOR`: add `currencyCode: MYR`; calculate new hash |
| `03-missing-required-store-name.json` | `ACCEPT` | T-02,T-04; L-01,L-02,L-04–L-06; S-01–S-03,S-05,S-06,S-08,S-09,S-11 | `HISTORICAL_SUCCESSOR`: add `currencyCode: MYR`; calculate new hash |
| `04-unresolved-purchase-date.json` | `ACCEPT` | T-02,T-04,T-07; L-01,L-02,L-04–L-06; S-01–S-03,S-05,S-06,S-08,S-09,S-11 | `HISTORICAL_SUCCESSOR`: add `currencyCode: MYR`; calculate new hash |
| `05-decimal-weighted-quantity.json` | `ACCEPT` | T-04,T-06; L-01,L-02,L-04–L-06; S-01–S-03,S-05,S-06,S-08,S-09,S-11 | `HISTORICAL_SUCCESSOR`: add `currencyCode: MYR`; calculate new hash |
| `06-processing-unavailable.json` | `ACCEPT` | T-07; L-06,L-07; S-04–S-07 | `HISTORICAL_BYTES_UNCHANGED`; SHA-256 `C5F74B21D43E6362FC500CB394D0210B0C7C55F5DBDF6B4C0C02AB9622AE3EB2` |
| `07-processing-failure.json` | `ACCEPT` | T-07; L-06,L-07; S-04–S-07,S-09 | `HISTORICAL_BYTES_UNCHANGED`; SHA-256 `97B665B8BAF4F464372222DD4B60BABE48314C5A7E9E718704009DE6725CE82E` |
| `08-unsupported-schema-version.json` | `REJECT_UNSUPPORTED_SCHEMA_VERSION` | T-01,T-07; L-02; S-07 | `HISTORICAL_BYTES_UNCHANGED`; SHA-256 `6338E21A41AC681015CBD665CA7E3D5EA8C3BE1A80DD3532DDEBF2C82D082E77` |
| `09-malformed-status-value.json` | `REJECT_CONTRADICTORY_FIELD_STATE` | T-01,T-02; L-02,L-04,L-05; S-02,S-06,S-09 | `HISTORICAL_SUCCESSOR`: add `currencyCode: MYR`, preserve the sole intended contradiction; calculate new hash |
| `15-result-available-extraction-failed.json` | `ACCEPT` | T-02,T-07; L-01,L-02,L-05–L-07; S-06,S-08,S-09,S-11 | `NEW_APPROVED_SCENARIO`; construct with genuine `OCR_PARTIAL` evidence and preserved `extractionStatus: FAILED`; calculate hash |
| `16-source-evidence-insufficient.json` | `ACCEPT` | T-07; L-03,L-04,L-06; S-04–S-06,S-09 | `NEW_APPROVED_SCENARIO`; genuine `OCR_COMPLETED` insufficient profile; calculate hash |
| `23-unit-price-three-decimals.json` | `REJECT_INVALID_MONEY` | T-01; L-02,L-05; S-01,S-02 | `NEW_APPROVED_SCENARIO`; one money-scale defect; calculate hash |
| `29-quantity-scale-four.json` | `REJECT_INVALID_QUANTITY` | T-01,T-06; L-02,L-05; S-02 | `NEW_APPROVED_SCENARIO`; one quantity-scale defect; calculate hash |
| `33-invalid-gregorian-date.json` | `REJECT_INVALID_DATE` | T-01,T-07; L-02,L-05; S-02 | `NEW_APPROVED_SCENARIO`; one calendar defect; calculate hash |
| `36-unknown-envelope-member.json` | `REJECT_UNKNOWN_MEMBER` | T-01,T-07; L-02; S-07 | `NEW_APPROVED_SCENARIO`; one undeclared top-level member; calculate hash |
| `38-duplicate-json-key.json` | `REJECT_DUPLICATE_JSON_KEY` | T-01,T-07; L-02; S-07 | `NEW_APPROVED_SCENARIO`; raw bytes contain one duplicate `schemaVersion`; calculate hash without parsing/reserializing |
| `44-request-context-mismatch.json` | `REJECT_REQUEST_ID_MISMATCH` | T-01,T-07; L-03; S-04 | `NEW_APPROVED_SCENARIO`; non-null fixture consumer context; calculate hash |
| `45-image-context-mismatch.json` | `REJECT_IMAGE_ID_MISMATCH` | T-01,T-07; L-03; S-04 | `NEW_APPROVED_SCENARIO`; non-null fixture consumer context; calculate hash |
| `57-unknown-token-reference.json` | `REJECT_UNKNOWN_TOKEN_REFERENCE` | T-01,T-02; L-04; S-09 | `NEW_APPROVED_SCENARIO`; one absent projected token ID; calculate hash |
| `65-result-with-insufficient-gate.json` | `REJECT_GATE_OUTCOME_MISMATCH` | T-07; L-06; S-06 | `NEW_APPROVED_SCENARIO`; available result with actual insufficient gate; calculate hash |
| `67-result-with-ocr-failed-evidence.json` | `ACCEPT` | T-07; L-01,L-03,L-04,L-06; S-04–S-06,S-08,S-09,S-11 | `NEW_APPROVED_SCENARIO`; derive from genuine structurally valid synthetic Contract V0 output; calculate hash |
| `67a-result-with-received-evidence.json` | `ACCEPT` | T-07; L-01,L-03,L-04,L-06; S-04–S-06,S-08,S-09,S-11 | `NEW_APPROVED_SCENARIO`; derive from genuine structurally valid synthetic Contract V0 output; calculate hash |
| `75-source-evidence-insufficient-partial.json` | `ACCEPT` | T-07; L-03,L-04,L-06; S-04–S-06,S-09 | `NEW_APPROVED_SCENARIO`; genuine `OCR_PARTIAL` insufficient profile; calculate hash |
| `76-source-evidence-insufficient-received.json` | `ACCEPT` | T-07; L-03,L-04,L-06; S-04–S-06,S-09 | `NEW_APPROVED_SCENARIO`; genuine `RECEIVED` insufficient profile; calculate hash |
| `77-source-evidence-insufficient-ocr-failed.json` | `ACCEPT` | T-07; L-03,L-04,L-06; S-04–S-06,S-09 | `NEW_APPROVED_SCENARIO`; genuine `OCR_FAILED` insufficient profile; calculate hash |
| `s06-02-source-gate-failure-after-completed-ocr.json` | `ACCEPT` | T-07; L-06,L-07; S-06 | `NEW_APPROVED_SCENARIO`; source-gate stage, completed evidence, no recorded gate; calculate hash |
| `s06-04-extraction-failure-after-completed-ocr-and-sufficient-gate.json` | `ACCEPT` | T-07; L-06,L-07; S-06 | `NEW_APPROVED_SCENARIO`; extraction stage with genuine sufficient gate; calculate hash |
| `s06-06-presentation-adapter-failure-after-completed-ocr.json` | `ACCEPT` | T-07; L-06,L-07; S-06 | `NEW_APPROVED_SCENARIO`; backend adapter stage with genuine sufficient gate; calculate hash |
| `s06-26-ocr-failure-with-received-evidence.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | T-07; L-06; S-06 | `NEW_APPROVED_SCENARIO`; one prohibited OCR-stage evidence status; calculate hash |
| `s06-29-source-gate-failure-with-ocr-failed-evidence.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | T-07; L-06; S-06 | `NEW_APPROVED_SCENARIO`; one prohibited gate-stage evidence status; calculate hash |
| `s06-18-extraction-failure-with-ocr-failed-evidence.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | T-07; L-06; S-06 | `NEW_APPROVED_SCENARIO`; one prohibited extraction-stage evidence status; calculate hash |
| `s06-32-presentation-adapter-failure-with-ocr-failed-evidence.json` | `REJECT_EVIDENCE_STAGE_MISMATCH` | T-07; L-06; S-06 | `NEW_APPROVED_SCENARIO`; one prohibited adapter-stage evidence status; calculate hash |

Fixtures 67 and 67a must be projected from genuine structurally valid synthetic
Contract V0 objects; they must not be relabeled invalid envelopes. The deferred
post-insufficient projection exception is a non-JSON lifecycle case and is not
allowlisted here.

### 6.1 Manifest and hash method

For every fixture, `manifest.json` must record:

- path relative to the V1 root, always `fixtures/<filename>.json`;
- exact expected result code;
- applicable decision IDs;
- lowercase SHA-256 of raw bytes;
- byte length; and
- one source classification: `HISTORICAL_BYTES_UNCHANGED`,
  `HISTORICAL_SUCCESSOR`, or `NEW_APPROVED_SCENARIO`.

Hash raw UTF-8 bytes exactly as stored, including newline bytes. Never
parse/reserialize before hashing. Both harnesses must fail on a hash mismatch,
missing listed fixture, unlisted JSON fixture, manifest/fixture expected-result
disagreement, duplicate manifest path, or zero executed fixtures.

The initial shared set is deliberately not described as complete coverage of
the full fixture-expansion proposal. Language-local tests must still cover
remaining boundaries such as quantity zero, invalid ID grammar, unsafe
provenance, role ordering, required-null distinction, unsupported currency,
other S-06 accepted/forbidden status combinations, BOM, malformed UTF-8,
comments, trailing commas, and trailing content.

## 7. Technical requirements, dependencies, and API 26

Both implementations must:

- accept raw bytes and reject UTF-8 BOM, malformed UTF-8, invalid JSON,
  duplicate keys, comments, trailing commas/content, and nonstandard numbers;
- reject unknown members and enums without type coercion;
- require explicit nullable members rather than treating absence as null;
- preserve array order and enforce exact role order and uniqueness;
- keep all protocol IDs opaque, case-sensitive, privacy-safe, and correlated to
  caller-supplied request/image IDs;
- keep money and quantity as strings, validate with regex plus arbitrary
  precision decimal, and never round or use binary floating point;
- accept only exact two-decimal non-negative MYR money and positive quantity
  with maximum scale three;
- validate canonical ISO dates lexically and against the Gregorian calendar;
- preserve immutable original automatic values and Contract V0 extraction
  status without recomputing completeness;
- require `automaticExtraction.stage` to be exactly `PRE_REVIEW_AUTOMATIC`,
  treat `producerId` as opaque and case-sensitive, and require a nonblank
  `producerVersion`;
- validate field-state/value/reason/confidence/token combinations and token
  registry references;
- implement exactly four terminal outcomes and the approved S-06 matrix;
- conditionally accept all four source-processing statuses for available and
  insufficient-evidence results while retaining narrower technical-failure
  restrictions;
- omit external unit-price reference evidence and make no correctness claim;
  and
- keep the post-insufficient projection exception outside JSON conformance.

Android-specific requirements:

- remain free of Android framework types so JVM tests exercise the same logic;
- use a strict `CharsetDecoder` with `CodingErrorAction.REPORT`;
- use API-26-safe defensive copies, `BigDecimal`, `MessageDigest`, regex, and
  `LocalDate`; do not use Java APIs unavailable at API 26;
- use `Double` only for finite `nativeConfidence` parsing; and
- never map decimal receipt quantity to integer inventory.

Python-specific requirements:

- use `json.loads` with duplicate-aware `object_pairs_hook` and a rejecting
  `parse_constant` before ordinary dictionary construction;
- use `Decimal`, exact regex, and `date.fromisoformat` after lexical date checks;
- validate projected token IDs against actual V0 evidence in the test projector;
- require the test projector's producer ID as an explicit caller input and
  preserve `ReceiptOutput.extractor_version` as the producer version;
  and
- never emit raw source paths/URIs, OCR text/geometry, participant/evaluation
  IDs, or external-price evidence.

## 8. Exact verification commands

### 8.1 Kotlin/JVM and Android

From `D:/PantryProof/mobile/android`:

```powershell
.\gradlew.bat :app:testDebugUnitTest --tests "com.pantryproof.prototype.contract.v1.*"
.\gradlew.bat :app:testDebugUnitTest
.\gradlew.bat :app:assembleDebug
.\gradlew.bat :app:lintDebug
.\gradlew.bat :app:connectedDebugAndroidTest
.\verify-android.ps1 -DeviceSerial <API26-emulator-serial>
.\verify-android.ps1 -DeviceSerial <API36-emulator-serial>
```

Acceptance requires the new conformance tests plus the unchanged baseline of 15
existing unit tests and 13 instrumentation tests. No new instrumentation test is
required because M3E-1 remains disconnected from production UI/navigation.

### 8.2 Python

From `D:/PantryProof`:

```powershell
python -m unittest discover -s tests -p "test_presentation_v1_*.py" -v
python -m unittest tests.test_contracts tests.test_ocr_adapter -v
python -m unittest discover -s tests -p "test_*.py" -v
```

### 8.3 Shared fixture hash and parity audit

```powershell
$fixtureRoot = "D:\PantryProof\tests\fixtures\receipt_presentation_v1\v1"
$manifest = Get-Content -Raw -LiteralPath "$fixtureRoot\manifest.json" | ConvertFrom-Json
foreach ($entry in $manifest.fixtures) {
    $path = Join-Path $fixtureRoot $entry.path
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actual -ne $entry.sha256) { throw "Fixture hash mismatch: $($entry.path)" }
}
```

Cross-language parity is established only when both manifest-driven test suites
consume the same 32 canonical files, execute a nonzero count, verify the same
raw-byte hashes, and produce the manifest's same expected result code for every
fixture. A passing test run against copied or regenerated JSON does not qualify.

## 9. Independent implementation review requirements

No M3E-1 implementation is ready for Git integration until a reviewer other
than the relevant implementer records the following checks.

### 9.1 Android review

- Confirm only the Tai/shared allowlisted paths changed.
- Confirm the pinned dependency is only `jackson-core:2.21.8` and strict parser
  features are explicitly configured rather than assumed.
- Confirm immutable DTOs preserve original values/provenance and remain isolated
  from UI models, `MainActivity`, review, inventory, and mock sources.
- Confirm correlation is caller-supplied and case-sensitive.
- Confirm all fixture bytes are hash-checked before decoding.
- Run targeted tests, full unit/build/lint, and API 26/API 36 regression.

### 9.2 Backend review

- Confirm duplicate keys are rejected before ordinary dictionary creation.
- Confirm exact member sets, explicit nulls, value grammar, ordering, S-06, and
  S-09 token/state rules match the approved precedence documents.
- Confirm V0 extraction status and identities are preserved, not recomputed.
- Confirm the projector accepts only genuine synthetic V0 evidence/output and
  cannot import or invoke B1/B2/B3, OCR orchestration, proposed, or evaluation.
- Confirm raw provenance and sensitive/evaluation content cannot be emitted.
- Run targeted, Contract V0, and full Python regressions.

### 9.3 Shared parity review

- Confirm the 32-file allowlist exactly matches `manifest.json`, with no missing
  or extra JSON files and no zero-test success.
- Review every successor/new fixture for a single intended defect or valid
  construction and verify original nine draft bytes remain unchanged.
- Independently recompute hashes and compare Kotlin/Python result-code summaries.
- Confirm no fixture or validator represents the deferred post-insufficient
  projection exception or introduces a fifth outcome.

Review findings must be evidence-backed `PASS`, `FAIL`, or `BLOCKED`; file
presence or implementer self-assertion is not independent approval.

## 10. Decisions still required before coding

Only these narrowly scoped approvals remain:

1. **Tai implementation approval:** approve the seven-path Android allowlist,
   including the single existing-file edit adding pinned
   `jackson-core:2.21.8`.
2. **Leng implementation approval:** approve the five new Python/test paths and
   the test-only placement of the synthetic Contract V0 projector.
3. **Joint shared-fixture approval:** approve the one canonical path, two shared
   metadata files, and exact 32-fixture allowlist/outcomes in Section 6.

No methodology decision is reopened. Any additional source, test, fixture,
dependency, build-file, runtime adapter, or contract change is outside this
scope and requires a new explicit review.

## 11. Copy-ready independent implementation authorization statements

These statements are templates. This document does not execute them.

### 11.1 Tai authorization template

> **Owner:** Tai Yong Xin  
> **Scope candidate:** `M3E-1P-SCOPE-CANDIDATE-2026-11-05`  
> **Decision:** APPROVE — NO EXCEPTIONS  
>  
> I approve the exact Tai-owned Android and shared-fixture implementation scope
> in `mobile/android/verification/m3e/m3e-1p-implementation-scope-lock.md`.
> I authorize only the six new Kotlin/test files, the one reviewed
> `mobile/android/app/build.gradle.kts` edit adding
> `com.fasterxml.jackson.core:jackson-core:2.21.8`, and the exact shared files
> listed in Sections 5 and 6. I approve the canonical shared-fixture location,
> expected outcomes, raw-byte hashing requirements, API 26 constraints,
> regression commands, and independent-review gate.  
>  
> I do not authorize UI activation, `MainActivity`, existing UI models or
> validators, runtime receipt sources, fixture expansion beyond the allowlist,
> OCR, backend integration, persistence, scoring, calibration, evaluation,
> real-receipt processing, or protected-contract changes.  
>  
> **Decision:** `TAI_M3E_1_IMPLEMENTATION_SCOPE_APPROVED`  
> **Exceptions:** None.

### 11.2 Leng authorization template

> **Owner:** Leng Wei Heng  
> **Scope candidate:** `M3E-1P-SCOPE-CANDIDATE-2026-11-05`  
> **Decision:** APPROVE — NO EXCEPTIONS  
>  
> I approve the exact Leng-owned Python/test and shared-fixture implementation
> scope in
> `mobile/android/verification/m3e/m3e-1p-implementation-scope-lock.md`. I
> authorize only the five new Python/test files and exact shared files listed in
> Sections 5 and 6. I approve the test-only synthetic Contract V0 projection
> boundary, canonical shared-fixture location, expected outcomes, raw-byte hash
> requirements, full source/token/identity validation, regression commands, and
> independent-review gate.  
>  
> I do not authorize changes to Contract V0, OCR/source-gate orchestration,
> B1/B2/B3, proposed-method/evaluation code, production projection/runtime
> integration, fixture expansion beyond the allowlist, persistence, scoring,
> calibration, evaluation, or real-receipt processing.  
>  
> **Decision:** `LENG_M3E_1_IMPLEMENTATION_SCOPE_APPROVED`  
> **Exceptions:** None.

## Final status

`M3D_CONTRACT_DESIGN_JOINTLY_APPROVED`

`LENG_M3E_1_DIRECTION_APPROVED`

`M3E_1_IMPLEMENTATION_SCOPE_PENDING_APPROVAL`

`SYNTHETIC_CONFORMANCE_IMPLEMENTATION_NOT_YET_AUTHORIZED`

`REAL_BACKEND_ACTIVATION_NOT_READY`

`PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`
