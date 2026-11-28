# PantryProof Android UI prototype

**ANDROID_UI_PROTOTYPE — SYNTHETIC_DEMO_DATA — BACKEND_NOT_INTEGRATED**

This directory contains the current self-contained Kotlin Android prototype,
including O07 image handling, I2C synthetic processing, I2D inventory browsing,
I2E session assurance and the retained I2F readiness audit. It does not import
Python runtime or evaluation modules, access research receipts, or claim that
OCR/correction/persistence is operational.

## Stack and entry point

- Module: mobile/android/app
- Language: Kotlin
- UI: native Android Views created by MainActivity
- Minimum SDK: 26
- Compile/target SDK: 36
- Entry point: app/src/main/java/com/pantryproof/prototype/ui/MainActivity.kt

Kotlin/native Android Views were selected because the repository did not contain
an existing Android or Flutter application to preserve. MainActivity owns screen
navigation and rendering; PantryUiState owns session receipt, confirmation and
inventory state. ReceiptPresentationSource remains the existing demo-data seam.
The frozen Presentation V1 decoder/validator, M3E adapter and I1 request
coordinator are reused by the I2C lifecycle. Dedicated UI controllers and
synthetic transports keep processing results separate from inventory admission.
Operational Android/Python execution and transport remain separate integration
decisions.

## Navigation flow

Dashboard → Add receipt → Use synthetic demo → Receipt Preview → Receipt Details
→ Manual Review/edit → Explicit temporary confirmation → Inventory.

The dashboard also links directly to this editable synthetic receipt path,
session inventory, and the independent Synthetic Processing Demo. The processing
routes are distinct:

- Dashboard → Synthetic Processing Demo → Ready → Explicit Start → Read-only
  fictional processing result. This route does not use a selected photograph.
- Add receipt → Gallery or camera → Preview/crop → Test selected image processing
  → Local snapshot preparation → Ready → Explicit Start → Read-only fictional
  processing result. The fields are not extracted from the selected image.

Preview also retains manual receipt entry, validation and review before explicit
session-only confirmation. Neither processing-result page edits, confirms or
adds its returned receipt to inventory. Back navigation remains available,
including discard warnings for unsaved review/manual changes.

## Data and integration boundary

ReceiptPresentationSource is the UI-facing integration seam.
MockReceiptPresentationSource supplies one deterministic fictional receipt and
fictional inventory. The sample covers store name, purchase date, description,
quantity, optional unit price, line total, and receipt total. One item
intentionally has no unit price.

Gallery selection uses Android's Photo Picker on Android 13+ and
ACTION_OPEN_DOCUMENT on earlier supported versions. Camera capture delegates to
an external camera activity through a non-exported FileProvider, using scoped
URI grants for app-owned receipt_camera cache files. Cancelled camera output,
replaced captures and orphaned owned cache files are cleaned up. Gallery access
tracks and releases only owned grants; picker cancellation preserves the previous
selection. The user's original gallery image is not deleted.

Selected-image processing prepares a sampled, orientation-corrected PNG in
memory off the main thread. The selected crop uses the same normalized,
orientation-corrected coordinates as Preview; full-image and cropped selections
remain distinct. JPEG EXIF orientation and ordinary PNG/WebP input are supported;
PNG/WebP containing EXIF are rejected rather than silently misoriented. Snapshot
preparation limits are 16 MiB encoded input, at most 16,384 pixels per source
dimension and 64 million source pixels, at most 1600 pixels per decoded
dimension, and 4 MiB retained PNG bytes. These are per-preparation bounds, not a
global process/native-memory guarantee or full-resolution preservation claim.
Empty, unsupported, unreadable, missing or oversized inputs fail locally before
submission; no successful synthetic result is manufactured from an image error.

O07 snapshots defensively retain bytes and bind to the exact I2C selection and
request identities. Both processing pages use the existing lifecycle, worker
validation and queued UI delivery, with independently supplied request/image
identities and FIXTURE mode. Preparing/selecting input never submits it. Start
is explicit, Pending prevents duplicate submission, Cancel returns to Ready,
and replacing input/crop or leaving the page invalidates prior work. Late or
duplicate callbacks cannot overwrite the current admitted result. The 10-second
interactive deadline is demo configuration, not an operational backend policy.

Valid V1 outcomes remain distinct from rejection and local missing-response,
timeout or execution failures. Available results preserve missing/unresolved
fields, row order and exact decimal presentation strings. An Available result
with extraction status FAILED remains reviewable, with "Review receipt fields"
and "Automatic extraction needs manual review." It is not a technical processing
failure or evidence of OCR success. Selected-image results explicitly state:
"Synthetic test result — these fields were not extracted from your selected image."
No image bytes are uploaded or passed to Python.

Edits and inventory quantity changes remain session-only. Saved-instance state
restores the current flow, selected URI reference/crop, unsaved review/manual
draft, applied temporary receipt, confirmation state, inventory quantities and
inventory browse controls after ordinary Activity recreation. Processing owners
are disposed on backgrounding, exit or destruction. Returning/recreating uses a
fresh owner and, for selected images, fresh local preparation if input remains
readable; old pending requests are not restored or automatically resubmitted.
System process death was not exercised and is not claimed as equivalent coverage.
This is not durable storage: force-stop, app-data
clearing, uninstalling or a fresh launch without saved-instance state resets the
prototype.

The current merged manifests request no Internet, camera or storage permission;
camera/gallery access uses the scoped system flows above. allowBackup=false and
the packaged backup/cloud/device-transfer exclusion rules express the prototype
boundary, but OEM backup/device-transfer behavior has not been verified. Bundle
saved state is Android-managed; temporary captures, system/framework metadata
and ignored test artifacts must not be confused with a persistent inventory
database or a guarantee of no disk writes. Application code does not log receipt
payloads, image bytes or sensitive URI values. No network transport, OCR runtime
or inventory database is activated.

## Build and test

From mobile/android:

    .\gradlew.bat :app:assembleDebug
    .\gradlew.bat :app:testDebugUnitTest
    .\gradlew.bat :app:lintDebug
    .\gradlew.bat :app:assembleRelease
    .\gradlew.bat :app:connectedDebugAndroidTest

These are the standard tasks. The retained I2F audit used existing offline
dependencies and an ignored init script to redirect outputs and exclude the
separate L05 Kotlin consumption class. The generic unit-test task above does not
apply that exclusion automatically.

**L05-S01: ACCEPTED — CLOSED**

**L05-S02: ACCEPTED WITH EXACT LIMITATIONS — CLOSED**

L05-S02 verified original-byte genuine offline PaddleOCR output consumption
through the strict Kotlin Presentation V1 validator and M3E adapter, using
generated synthetic-image evidence. This is consumer verification, not an
operational Android-to-Python connection or OCR running in the mobile app.
The producer run was not independently reproduced; transferred-provenance and
missing raw-observer/source-snapshot limitations remain. The test source is
retained, but execution requires the original private source-bound ZIP at this
repository-relative location:

    artifacts/tai-l05-s02-consumption-20261119-01/received/pantryproof-l05-s02-source-bound-v1-transfer.zip

The archive contains eight original members, including the 4,172-byte sufficient
V1 payload and the 890-byte insufficient V1 payload. It is not automatically
available in a clean Git checkout. The accepted focused Kotlin consumer
verification passed 20 tests; this is retained evidence, not a new I2Q run.
The ZIP is 19,246 bytes with SHA-256
`faa6c0aa47da6497fef92ed667667aa8ce39c8d8149444f555e21ae315c6f85c`.
It is intentionally ignored and must be obtained through approved private
custody, not committed, reconstructed or replaced by synthetic vectors. The
unchanged test fails when that evidence is missing; this does not reopen the
accepted milestone. The unfiltered JVM task and standard verifier below require
that evidence when the L05 class is present.

For source-only JVM verification without L05 evidence or the separately owned
scoring inputs, this explicit selection covers the current accepted class set:

    .\gradlew.bat :app:testDebugUnitTest --tests 'com.pantryproof.prototype.contract.v1.ReceiptPresentation*' --tests 'com.pantryproof.prototype.contract.v1.L03KotlinPythonSyntheticParityTest' --tests 'com.pantryproof.prototype.data.*' --tests 'com.pantryproof.prototype.image.*' --tests 'com.pantryproof.prototype.ui.*' --no-daemon --console=plain --rerun-tasks

This selection was checked against the retained 18-class R1 inventory; this
exact command has not been newly executed for the documentation update. I2O used
an isolated init filter to exclude L05. Future test additions require rechecking
the selected class population. Do not silently skip L05 in an evidence-assisted
run: after verified private transfer, run its focused class explicitly:

    .\gradlew.bat :app:testDebugUnitTest --tests 'com.pantryproof.prototype.contract.v1.L05RealOcrV1KotlinConsumptionTest' --no-daemon --console=plain --rerun-tasks

For a repeatable local run against one already-booted emulator, use:

    .\verify-android.ps1

When more than one device is online, select one explicitly:

    .\verify-android.ps1 -DeviceSerial emulator-5554

Physical devices are rejected by default. If a physical test device is
deliberately selected, explicit opt-in is required:

    .\verify-android.ps1 -DeviceSerial <physical-serial> -AllowPhysicalDevice

This opt-in matters because instrumentation uses Android Test Orchestrator with
`clearPackageData=true`, which can clear the installed PantryProof test
application's local data. Never point this workflow at a participant or
production application installation.

The verifier confirms the SDK tools, selected device, completed boot, and AVD
identity; checks every ADB command outcome; wakes and dismisses the PIN-free
test keyguard; runs each Gradle task separately; reports every exit code; and
parses the unit/instrumentation XML. It
fails when instrumentation executes zero tests, so `NO-SOURCE` is never accepted
as success. Following Espresso's device guidance, it temporarily disables the
three device animation scales and restores each successfully modified setting
independently in a `finally` block. Restoration is read back and verified, and
one restoration failure does not prevent attempts to restore the remaining
settings. It does not start or stop emulators, delete outputs, or intentionally
leave device settings changed. Start an AVD listed by `emulator -list-avds`
before running it.

Instrumentation uses Android Test Orchestrator with `clearPackageData=true`.
Every scenario therefore runs in its own instrumentation invocation with fresh
application data, while individual scenarios still exercise their own
Activity-recreation and in-memory state behavior.

By default, Gradle generates artifacts in these locations; isolated audit runs
may redirect outputs to their ignored evidence directories:

- APK: `app/build/outputs/apk/debug/app-debug.apk`
- Unsigned release APK: `app/build/outputs/apk/release/app-release-unsigned.apk`
- Unit XML/HTML: `app/build/test-results/testDebugUnitTest` and
  `app/build/reports/tests/testDebugUnitTest`
- Lint XML/HTML: `app/build/reports/lint-results-debug.xml` and
  `app/build/reports/lint-results-debug.html`
- Instrumentation XML/HTML: `app/build/outputs/androidTest-results/connected/debug`
  and `app/build/reports/androidTests/connected/debug`

The M2D manual accessibility outcomes and synthetic-only focus captures are
documented under `verification/m2d`. The report distinguishes verified
TalkBack focus/navigation from spoken output that still requires a human
listening pass.

## Verified Android versions

The retained I2F readiness audit on **19 November 2026** verified the current
local worktree on Android 8.0 / API 26 and Android 16 / API 36. These are dated
local execution results, not GitHub CI results or guaranteed future test counts:

| I2F verification | Retained result |
|---|---|
| Android JVM, excluding L05 | 255 passed; zero failures, errors or skips |
| API 26 instrumentation | 77 passed; zero failures, errors or skips |
| API 36 instrumentation | 77 passed; zero failures, errors or skips |
| Debug assembly, twice | Successful; byte-identical APKs on the installed toolchain/cache |
| Unsigned release assembly | Successful; not signed or distribution-ready |
| Lint | Zero errors; 14 warnings |

The audit used AGP 8.13.2, Kotlin 2.2.20, Gradle 8.14, JDK 21.0.9, JVM target 17
and build tools 35.0.0, with minSdk 26 and compile/targetSdk 36. Debug signing
reused the existing debug key; no release key was generated. Repeatability on
this machine does not establish clean-machine or hermetic reproducibility.

Both emulator runs covered the current processing pages, generated gallery/camera
result handling, crop/snapshot boundaries, manual/demo review, temporary
inventory, I2D browsing and I2E journeys. Actual system picker launch/cancellation
and inventory-query preservation through rotation were also checked. Automated
coverage includes narrow layouts, 200% font scaling, focus/keyboard behavior,
accessible labels, touch targets and polite status/count updates. Controlled
camera results are not physical-camera validation. Audit settings were restored
and only audit-owned emulators were stopped. The I2F run overrode the normal
clearPackageData default to false on isolated emulator state; the standard
verifier's destructive-data warning above still applies.

Retained private local evidence, when present in this checkout:

- I2C UI closure: `../../artifacts/tai-ui-i2c-final-emulator-20261118-01/`.
- O07 selected-image handoff: `../../artifacts/tai-selected-image-20261118-01/`.
- I2D inventory implementation/final preservation: `../../artifacts/tai-inventory-browse-20261118-01/`.
- I2E session assurance: `../../artifacts/tai-i2e-session-assurance-20261119-01/`.
- I2F readiness report, commands, XML, APK hashes and limitations:
  `../../artifacts/tai-i2f-readiness-20261119-01/RESULT.md`.

These ignored records may be absent from a clean clone. The latest implementation
has no physical-device verification, no manual TalkBack session, no proven
process-death recovery, no completed OEM backup/device-transfer assessment and
no signed production release. Automated accessibility checks do not replace
human screen-reader evaluation. I2F is prototype readiness, not production
deployment approval or evaluation freeze.

The retained I2J automated instrumentation passed 88 tests per API, and I2K
passed 94 per API, on API 26 and API 36. These cover inventory focus restoration
and independent keyboard/accessibility-focus channels on the processing pages.
They establish automated focus state, not audible reader navigation or speech.
**MANUAL_TALKBACK_SPEECH_NOT_VERIFIED**

The later I2O controlled reproduction, accepted with exact limitations on
**20 November 2026**, used HEAD plus the exact 27-file accepted Android overlay.
The baseline commit `557208274ecbbc724ac481aed34bff500d85bde2` alone does not
contain the entire accepted Android implementation. It was a controlled source
snapshot, not a clean Git clone. R01 and R02 retained these separate local
results, not GitHub CI results or new tests executed in I2Q:

| I2O verification | Retained result |
|---|---|
| HEAD archive | 272 exact committed-file identities |
| Accepted source overlay | 27 matching hashes |
| Controlled snapshot | 292 source files |
| Source-only JVM, excluding L05 and separately owned scoring tests | 248 passed; zero failures, errors or skips |
| API 26 instrumentation, R02 | 94 passed; zero failures, errors or skips |
| API 36 instrumentation, R01 | 94 passed; zero failures, errors or skips |
| Evidence-assisted L05 Kotlin consumption, R01 | 20 passed; zero failures, errors or skips |
| Debug assembly | Successful |
| Lint | Zero errors; 14 warnings |

The historical 255-test JVM total included seven separately owned scoring cases;
those two scoring files were excluded from the controlled source set. The 248
and focused 20 results were separate executions, not a new combined full-suite
run. Original L05 bytes were consumed without running Python or PaddleOCR again.
This verifies the Kotlin consumer boundary, not Android OCR or a backend link.
Installed toolchain/dependency caches and a historically passing API 26 AVD
context were used; clean-machine and clean-AVD reconstruction are not proven.
API 26 was successfully reproduced in I2O-R02 after the earlier isolated AVD boot
problem; those failed attempts remain diagnostic evidence. Manual TalkBack
speech, physical-device and other limitations above remain unchanged.

The earlier M3A results below are preserved as historical evidence, not the
verification count for the current implementation.

**API26_VERIFIED** — On 2026-11-04 the complete workflow ran on Android 8.0 /
API 26 using the official `system-images;android-26;google_apis;x86_64` image:
debug assembly and lint passed, all 15 unit tests passed, and all 13
instrumentation tests passed. The real `ACTION_OPEN_DOCUMENT` picker was also
opened and cancelled successfully on the isolated API 26 AVD. The app-scoped
synthetic image fixture required no shared-storage permission.

The same post-fix suite passed on Android 16 / API 36 with 15 unit and 13
instrumentation tests. API 26 and API 36 XML/HTML reports and synthetic-only
screenshots are preserved under `verification/m3a`. Audible TalkBack speech and
high-contrast rendering remain hardware/environment verification gaps rather
than claims of completed accessibility coverage.

The local machine needs JDK 17 or newer and Android SDK platform 36. Set
ANDROID_HOME or provide an ignored local.properties when the SDK is not
discovered automatically.

## Implemented

- Dashboard and complete mock navigation flow.
- M2A semantic light-theme colors, typography, spacing, shape, action, banner,
  progress-header, and state-panel components for native Android Views.
- Redesigned Home, Add Receipt, and Receipt Preview screens with a four-stage
  progress treatment, truthful local/synthetic source states, unavailable-camera
  presentation, and source-aware actions.
- Gallery selection, guarded URI preview and app-owned temporary camera capture.
- O07 orientation/crop handling, bounded sampled snapshots and exact
  selection/request binding without upload or OCR.
- Picker cancellation returns to the current screen without changing source
  state; selected URI, preview message, current screen, and navigation stack are
  restored across ordinary Activity recreation.
- Explicit synthetic/selected-image labeling.
- Independent I2C Synthetic Processing Demo and separate selected-image
  processing demonstration, both with explicit Start/Cancel, current-selection
  admission, read-only fictional results and no inventory confirmation.
- Frozen V1 validation/M3E mapping, extraction-status propagation and the RB08
  manual-review annotation for Available results with extraction status FAILED.
- Display of all seven core receipt fields with Malaysian ringgit formatting.
- Optional/missing unit-price display.
- M2B semantic Receipt Details, Manual Review and Household Inventory screens,
  including stacked metrics for compact/large-text layouts.
- Persistent form labels and RM prefixes, inline errors, error summary, first-error
  focus, temporary apply, confirmed discard, and confirmed sample revert behavior.
- Inline local-demo confirmation with no separate destination and no backend or
  persistence claim.
- Manual receipt entry with validation, arithmetic review warnings, explicit
  review/confirmation and duplicate-row protection for session-only manual rows.
- Session inventory with accessible 48 dp controls and in-memory quantities
  bounded from 0 to 99, still targeted by exact item ID after filtering/sorting.
- I2D case-insensitive, whitespace-trimmed product-name search and Clear;
  original/name/quantity sorting with stable ties; baseline/demo, temporary
  receipt-preview and manual source filters; filtered/total counts and separate
  empty-inventory/no-results states. Projection does not mutate underlying stock
  or order; browse controls survive supported navigation and Activity recreation.
- Reconfirmation rebuilds receipt-derived preview rows from the current synthetic
  receipt without duplicating them, while retaining session-only adjustments to
  the baseline mock pantry rows by item ID.
- I2J inventory quantity-control focus restoration by stable item/action tags,
  and I2K independent keyboard/accessibility-focus preservation on both
  processing pages, with automated regressions and the speech limitation above.
- Pure unit tests for validation and presentation state.
- I2E cross-screen session journeys and I2F build/manifest/API compatibility
  verification, with dated evidence and limitations recorded above.

Representative M2A emulator captures are under `verification/m2a`. They use
only the deterministic synthetic UI and screenshots generated from that UI.

## Deferred

- Operational OCR, field extraction, model inference and proposed-method
  correction in the Android workflow.
- Android-to-Python image/backend transport and operational runtime orchestration.
- Live Python self-correction integration with the Android workflow.
- Automatic arithmetic reconciliation beyond the existing manual-review warnings.
- SQLite or other persistent inventory storage.
- Production receipt history and operational processing-status integration.
- Android activation of evaluation row matching, training, threshold fitting,
  scoring/calibration or held-out evaluation modules.
- Signed production release, deployment and research evaluation freeze.

The frozen Presentation V1 contract, canonical fixtures, strict consumer and M3E
adapter already exist. Future operational integration must reuse those boundaries
and obtain separate approval; synthetic lifecycle/image-ingress demonstrations
do not establish a live backend producer, remote cancellation, backend idempotency
or automatic inventory admission. No evaluation-only Python objects are imported.

**PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN**

**REAL_BACKEND_ACTIVATION_NOT_READY**
