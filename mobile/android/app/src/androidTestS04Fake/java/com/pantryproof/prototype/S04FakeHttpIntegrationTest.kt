package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.provider.MediaStore
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.S04FakeHttpTransport
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.SelectedImageProcessingController
import java.io.DataInputStream
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class S04FakeHttpIntegrationTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()

    @Test
    fun g1ReceivesAndRendersThePinnedF01Fixture() = withPreparedFixture("F01") { scenario ->
        scenario.onActivity { click(it, R.id.selected_processing_start) }
        awaitActivity(scenario, "S04 did not reach a terminal state") {
            controller(it)?.state is ReceiptProcessingLifecycle.State.Finished
        }
        scenario.onActivity { activity ->
            val finished = requireNotNull(controller(activity)?.state as? ReceiptProcessingLifecycle.State.Finished)
            val context = finished.request.context
            check(context.mode == PresentationConsumerMode.FIXTURE)
            check(context.expectedRequestId == F01_REQUEST_ID && context.expectedImageId == F01_IMAGE_ID)

            val presentation = finished.outcome as? ReceiptProcessingLifecycle.Outcome.Presentation
            val available = presentation?.result as? ReceiptPresentationUiResult.Available
            check(available != null) { "Expected an accepted F01 receipt presentation" }
            val itemNames = listOf("Beras Tempatan 5kg", "Susu UHT 1L")
            check(available.receipt.storeName.value == "Kedai Runcit Harmoni")
            check(available.receipt.items.map { it.description.value } == itemNames)

            val root = requireNotNull(activity.findViewById<View>(R.id.screen_selected_processing))
            val status = requireNotNull(root.findViewById<View>(R.id.selected_processing_status))
            check(status.hasText(activity.getString(R.string.presentation_available_title)))
            check(root.hasText("Kedai Runcit Harmoni") && itemNames.all { root.hasText(it) })
            check(root.findViewById<View>(R.id.review_confirm) == null)
            check(root.findViewById<View>(R.id.review_apply) == null)
        }
    }

    @Test
    fun cancelBeforeTransportHandoffRetiresTheFixture() = withPreparedFixture("B12A") { scenario ->
        scenario.onActivity { activity ->
            // Hold the UI turn so the lifecycle cannot admit the worker handoff before Cancel.
            click(activity, R.id.selected_processing_start)
            check(controller(activity)?.state is ReceiptProcessingLifecycle.State.Pending)
            click(activity, R.id.selected_processing_cancel)
        }
        instrumentation.waitForIdleSync()
        scenario.onActivity { activity ->
            val selected = requireNotNull(controller(activity))
            check(selected.state is ReceiptProcessingLifecycle.State.Ready && !selected.canStart)
            val start = requireNotNull(activity.findViewById<View>(R.id.selected_processing_start))
            check(!start.isEnabled)
            check(activity.findViewById<View>(R.id.selected_processing_progress) == null)
            check(activity.findViewById<View>(R.id.details_item_0) == null)
        }
    }

    private fun withPreparedFixture(
        vector: String,
        exercise: (ActivityScenario<MainActivity>) -> Unit,
    ) {
        val arguments = InstrumentationRegistry.getArguments()
        // The separately authorized runner selects one vector and supplies ephemeral run arguments.
        assumeTrue("An explicit S04 vector must be selected", arguments.getString("s04Vector") == vector)
        val target = instrumentation.targetContext
        check(target.packageName == TARGET_PACKAGE) { "S04 requires the isolated target APK" }
        val port = requireNotNull(arguments.getString("s04Port")) { "Missing approved S04 port" }
        require(port.matches(Regex("[1-9][0-9]{0,4}")) && port.toInt() <= 65_535) { "Invalid S04 port" }
        val token = requireNotNull(arguments.getString("s04Token")) { "Missing ephemeral S04 run token" }
        require(token.matches(Regex("[0-9a-f]{64}"))) { "Invalid S04 run token format" }

        readPinnedAsset("s04-generated-image-manifest.json", MANIFEST_BYTES, MANIFEST_SHA256)
        readPinnedAsset("s04-g2.png", PNG_BYTES, S04FakeHttpTransport.GeneratedImage.G2.sha256)
        val g1 = readPinnedAsset("s04-g1.png", PNG_BYTES, S04FakeHttpTransport.GeneratedImage.G1.sha256)
        val preview = File.createTempFile("s04-g1-", ".png", target.cacheDir)
        try {
            preview.writeBytes(g1)
            val previewUri = Uri.fromFile(preview)
            val config = S04FakeHarnessBinding.RunConfig(
                instrumentation = instrumentation,
                port = port,
                token = token,
                requestId = F01_REQUEST_ID,
                imageId = F01_IMAGE_ID,
                generatedImage = S04FakeHttpTransport.GeneratedImage.G1,
                responsePin = S04FakeHttpTransport.Fixture.F01,
                preparedBytes = g1,
            )
            runWithFixture(config, previewUri, exercise)
        } finally {
            check(!preview.exists() || preview.delete()) { "Could not remove the task-owned S04 preview" }
        }
    }

    private fun runWithFixture(
        config: S04FakeHarnessBinding.RunConfig,
        previewUri: Uri,
        exercise: (ActivityScenario<MainActivity>) -> Unit,
    ) {
        Intents.init()
        try {
            var ticket: S04FakeHarnessBinding.Ticket? = null
            var scenario: ActivityScenario<MainActivity>? = null
            try {
                instrumentation.runOnMainSync { ticket = S04FakeHarnessBinding.stage(config) }
                val staged = requireNotNull(ticket)
                val pickerAction = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    MediaStore.ACTION_PICK_IMAGES
                } else {
                    Intent.ACTION_OPEN_DOCUMENT
                }
                // Stub the preview result in-process. The sender uses config's independently pinned bytes.
                Intents.intending(hasAction(pickerAction)).respondWith(
                    ActivityResult(Activity.RESULT_OK, Intent().setData(previewUri)),
                )
                val launched = ActivityScenario.launch(MainActivity::class.java)
                scenario = launched
                var beforeInventory: List<InventoryItem>? = null
                launched.onActivity { activity ->
                    beforeInventory = inventory(activity)
                    S04FakeHarnessBinding.attach(staged, activity, previewUri)
                    click(activity, R.id.home_add_receipt)
                }
                onView(withId(R.id.add_import_image)).perform(click())
                awaitActivity(launched, "S04 generated preview was not selected") {
                    it.findViewById<View>(R.id.preview_process_selected)?.isEnabled == true
                }
                launched.onActivity { activity ->
                    click(activity, R.id.preview_process_selected)
                    check(controller(activity)?.isFixture == true) { "S04 binding was not claimed" }
                }
                awaitActivity(launched, "S04 pinned input did not become ready") {
                    controller(it)?.canStart == true
                }
                exercise(launched)
                launched.onActivity { activity ->
                    check(inventory(activity) == requireNotNull(beforeInventory)) { "S04 changed session inventory" }
                }
            } finally {
                try {
                    ticket?.let { issued -> instrumentation.runOnMainSync { S04FakeHarnessBinding.reset(issued) } }
                } finally {
                    scenario?.close()
                }
            }
        } finally {
            Intents.release()
        }
    }

    private fun readPinnedAsset(name: String, expectedSize: Int, expectedSha256: String): ByteArray {
        val bytes = ByteArray(expectedSize)
        DataInputStream(instrumentation.context.assets.open(name)).use { source ->
            source.readFully(bytes)
            check(source.read() == -1) { "S04 asset exceeds its approved size" }
        }
        val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") {
            "%02X".format(Locale.ROOT, it.toInt() and 0xff)
        }
        check(hash == expectedSha256) { "S04 asset differs from its approved byte identity" }
        return bytes
    }

    private fun awaitActivity(
        scenario: ActivityScenario<MainActivity>,
        failure: String,
        condition: (MainActivity) -> Boolean,
    ) {
        val deadline = SystemClock.elapsedRealtime() + 8_000L
        do {
            var reached = false
            scenario.onActivity { reached = condition(it) }
            if (reached) return
            SystemClock.sleep(25L)
        } while (SystemClock.elapsedRealtime() < deadline)
        error(failure)
    }

    private fun controller(activity: MainActivity): SelectedImageProcessingController? =
        activity.findViewById<View>(R.id.screen_selected_processing)?.tag as? SelectedImageProcessingController

    private fun inventory(activity: MainActivity): List<InventoryItem> {
        // Reuse the existing instrumentation convention for reading immutable inventory entries.
        val field = MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }
        return (field.get(activity) as PantryUiState).inventory.toList()
    }

    private fun click(activity: MainActivity, id: Int) {
        val view = requireNotNull(activity.findViewById<View>(id)) { "S04 test view is missing" }
        check(view.isEnabled && view.performClick()) { "S04 test action is unavailable" }
    }

    private fun View.hasText(expected: String): Boolean {
        if (this is TextView) return text.toString() == expected
        return this is ViewGroup && (0 until childCount).any { getChildAt(it).hasText(expected) }
    }

    private companion object {
        const val TARGET_PACKAGE = "com.pantryproof.prototype.s04fake"
        const val F01_REQUEST_ID = "request-synthetic-complete-001"
        const val F01_IMAGE_ID = "image-synthetic-complete-001"
        const val PNG_BYTES = 1_352
        const val MANIFEST_BYTES = 3_865
        const val MANIFEST_SHA256 = "C06ED10F6D50B82122C1549E5C6048F67DB576C5A5ECC70A1A4A58DD069A313E"
    }
}
