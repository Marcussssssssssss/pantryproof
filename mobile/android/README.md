# PantryProof Android UI prototype

**ANDROID_UI_PROTOTYPE — SYNTHETIC_DEMO_DATA — BACKEND_NOT_INTEGRATED**

This directory contains a self-contained Kotlin Android application for the
initial PantryProof UI milestone. It does not import Python runtime or evaluation
modules, access research receipts, or claim that OCR/correction/persistence is
operational.

## Stack and entry point

- Module: mobile/android/app
- Language: Kotlin
- UI: native Android Views created by MainActivity
- Minimum SDK: 26
- Compile/target SDK: 36
- Entry point: app/src/main/java/com/pantryproof/prototype/MainActivity.kt

Kotlin/native Android Views were selected because the repository did not contain
an existing Android or Flutter application to preserve. The FYP documentation
classifies the realized Android framework as unresolved. This implementation is
isolated and does not change that research decision.

## Navigation flow

Dashboard → Add receipt → Image preview → Synthetic receipt fields → Manual
review/edit → Inline temporary confirmation → Temporary inventory preview.

The dashboard also links directly to the synthetic review path and mock
inventory. Back navigation is available throughout, including a discard warning
for unsaved form changes.

## Data and integration boundary

ReceiptPresentationSource is the UI-facing integration seam.
MockReceiptPresentationSource supplies one deterministic fictional receipt and
fictional inventory. The sample covers store name, purchase date, description,
quantity, optional unit price, line total, and receipt total. One item
intentionally has no unit price.

Choosing a real image uses Android's Photo Picker on Android 13+ and
ACTION_OPEN_DOCUMENT on earlier supported versions. The image stays local and
is previewed only. The UI explicitly states that the synthetic fields are not
extracted from, or associated with, a selected image.

Edits and inventory quantity changes remain session-only. Saved-instance state
restores the current flow, selected URI reference, unsaved review draft, applied
temporary receipt, confirmation state and inventory quantities after ordinary
Activity recreation. System process death was not exercised and is not claimed
as equivalent coverage. This is not durable storage: force-stop, app-data
clearing, uninstalling or a fresh launch without saved-instance state resets the
prototype.

## Build and test

From mobile/android:

    .\gradlew.bat :app:assembleDebug
    .\gradlew.bat :app:testDebugUnitTest
    .\gradlew.bat :app:lintDebug
    .\gradlew.bat :app:connectedDebugAndroidTest

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

Latest generated artifacts remain in Gradle's standard locations:

- APK: `app/build/outputs/apk/debug/app-debug.apk`
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
- Android local image selection and guarded URI preview.
- Picker cancellation returns to the current screen without changing source
  state; selected URI, preview message, current screen, and navigation stack are
  restored across ordinary Activity recreation.
- Explicit synthetic/selected-image labeling.
- Display of all seven core receipt fields with Malaysian ringgit formatting.
- Optional/missing unit-price display.
- M2B semantic Receipt Details, Manual Review and Household Inventory screens,
  including stacked metrics for compact/large-text layouts.
- Persistent form labels and RM prefixes, inline errors, error summary, first-error
  focus, temporary apply, confirmed discard, and confirmed sample revert behavior.
- Inline local-demo confirmation with no separate destination and no backend or
  persistence claim.
- Mock inventory display with accessible 48 dp controls and in-memory quantities
  bounded from 0 to 99.
- Reconfirmation rebuilds receipt-derived preview rows from the current synthetic
  receipt without duplicating them, while retaining session-only adjustments to
  the baseline mock pantry rows by item ID.
- Pure unit tests for validation and presentation state.

Representative M2A emulator captures are under `verification/m2a`. They use
only the deterministic synthetic UI and screenshots generated from that UI.

## Deferred

- Production OCR and field extraction.
- Model inference, proposed-method correction, scoring, and calibration.
- Arithmetic/reconciliation decisions beyond basic input formatting.
- SQLite or other persistent inventory storage.
- Camera capture, receipt history, and processing-status integration.
- Evaluation row matching, training, threshold fitting, and held-out evaluation.
- A production Android/backend DTO and conformance adapter.

A future milestone should define and approve a small versioned Android receipt
DTO fixture, then implement a read-only adapter behind
ReceiptPresentationSource. It should not import evaluation-only Python objects.
