package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.media.ExifInterface
import android.net.Uri
import android.os.Build
import android.os.ParcelFileDescriptor.AutoCloseInputStream
import android.os.SystemClock
import android.provider.MediaStore
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.espresso.matcher.RootMatchers.isDialog
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.*
import com.pantryproof.prototype.image.ReceiptCrop
import com.pantryproof.prototype.image.ReceiptCropView
import com.pantryproof.prototype.image.SelectedImageSnapshotEncoder
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.SelectedImageProcessingController
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.hamcrest.Matchers.not
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SelectedImageProcessingInstrumentedTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private var scenario: ActivityScenario<MainActivity>? = null
    private var intents = false
    private val files = mutableListOf<File>()
    private var inventory: List<InventoryItem> = emptyList()
    private var receipt: Receipt? = null
    private var presentation: ReceiptPresentationUiResult? = null
    private var confirmed = false

    @After fun preservePantryAndDispose() {
        try {
            scenario?.onActivity { a ->
                val state = pantry(a)
                assertEquals(inventory, state.inventory); assertEquals(receipt, state.receipt)
                assertEquals(presentation, state.presentationResult); assertEquals(confirmed, state.demoConfirmed)
            }
        } finally {
            scenario?.close()
            if (intents) Intents.release()
            files.forEach { it.delete() }
        }
    }

    @Test fun gallerySnapshotIsReadyWithoutSubmissionAndResultIsExplicitFictionalReadOnly() {
        gallery(image())
        onView(withId(R.id.preview_continue)).perform(scrollTo()).check(matches(isEnabled()))
        openTest()
        assertSnapshotRegions()
        scenario!!.onActivity { assertTrue(controller(it).state is ReceiptProcessingLifecycle.State.Ready) }
        onView(withId(R.id.selected_processing_start)).perform(scrollTo(), click())
        awaitText("Validated synthetic receipt")
        onView(withText("0.750")).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withId(R.id.review_confirm)).check(doesNotExist())
        onView(withId(R.id.review_apply)).check(doesNotExist())
        scenario!!.onActivity { assertTrue(hasText(it.window.decorView, context.getString(R.string.selected_processing_fictional))) }
        onView(withId(R.id.selected_processing_start)).perform(scrollTo())
        val screen = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        context.cacheDir.resolve("selected-image-fictional-result.png").outputStream().use {
            screen.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        screen.recycle()
    }

    @Test fun cameraOutputCreatesSnapshotThroughTheActualCaptureResultPath() {
        val fixture = image(jpeg = true); launch(); Intents.init(); intents = true
        intending(hasAction(MediaStore.ACTION_IMAGE_CAPTURE)).respondWithFunction { request ->
            @Suppress("DEPRECATION")
            val uri = request.getParcelableExtra<Uri>(MediaStore.EXTRA_OUTPUT)!!
            context.contentResolver.openOutputStream(uri, "w")!!.use { it.write(fixture.readBytes()) }
            ActivityResult(Activity.RESULT_OK, null)
        }
        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_capture_image)).perform(scrollTo(), click())
        onView(withId(R.id.preview_process_selected)).check(matches(isEnabled()))
        openTest(); assertSnapshotRegions()
    }

    @Test fun previewCropIsAppliedToActualSnapshotPixels() {
        gallery(image()); crop(ReceiptCrop.from(floatArrayOf(0f, 0f, .5f, 1f))!!); openTest()
        scenario!!.onActivity { a ->
            val bitmap = decode(snapshot(a).copyBytes())
            assertEquals(50, bitmap.width); assertEquals(60, bitmap.height)
            assertRed(bitmap.getPixel(bitmap.width / 2, bitmap.height / 2))
            assertRed(bitmap.getPixel(bitmap.width - 2, bitmap.height / 2)); bitmap.recycle()
        }
        onView(withText(R.string.selected_processing_cropped)).check(matches(isDisplayed()))
    }

    @Test fun exifRotatedGalleryCropUsesOrientationCorrectedCoordinates() {
        val file = image(jpeg = true)
        orient(file, ExifInterface.ORIENTATION_ROTATE_90)
        gallery(file); crop(ReceiptCrop.from(floatArrayOf(0f, 0f, 1f, .5f))!!); openTest()
        scenario!!.onActivity { a ->
            val bitmap = decode(snapshot(a).copyBytes())
            assertEquals(60, bitmap.width); assertEquals(50, bitmap.height)
            assertRed(bitmap.getPixel(30, 25)); bitmap.recycle()
        }
    }

    @Test fun exifMirrorAndFullSelectionPreserveExpectedRegionContent() {
        val file = image(jpeg = true)
        orient(file, ExifInterface.ORIENTATION_FLIP_HORIZONTAL)
        val bytes = worker { SelectedImageSnapshotEncoder(context.contentResolver).encode(Uri.fromFile(file), ReceiptCrop.FULL) }
        val bitmap = decode(bytes)
        assertBlue(bitmap.getPixel(10, 30)); assertRed(bitmap.getPixel(90, 30)); bitmap.recycle()
    }

    @Test fun encoderRejectsEmptyUnsupportedAndOversizedInput() {
        worker {
            val encoder = SelectedImageSnapshotEncoder(context.contentResolver)
            for (bytes in listOf(byteArrayOf(), "not an image".toByteArray(), ByteArray(SelectedImageSnapshotEncoder.MAX_SOURCE_BYTES + 1))) {
                try { encoder.encodeBytes(bytes, ReceiptCrop.FULL); fail("Invalid image accepted") }
                catch (_: SelectedImageSnapshotEncoder.ImageInputException) { }
            }
            byteArrayOf(1)
        }
    }

    @Test fun encoderRejectsEncodedOutputAboveRetainedLimit() {
        val file = File(context.cacheDir, "selected-noise-${UUID.randomUUID()}.png").also { files.add(it) }
        val size = SelectedImageSnapshotEncoder.MAX_DECODED_DIMENSION
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val random = java.util.Random(7L)
        val pixels = IntArray(size * size) { Color.rgb(random.nextInt(256), random.nextInt(256), random.nextInt(256)) }
        bitmap.setPixels(pixels, 0, size, 0, 0, size, size)
        file.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }; bitmap.recycle()
        assertTrue(file.length() > SelectedImageSnapshotEncoder.MAX_RETAINED_BYTES)
        assertTrue(file.length() < SelectedImageSnapshotEncoder.MAX_SOURCE_BYTES)
        worker {
            try {
                SelectedImageSnapshotEncoder(context.contentResolver).encode(Uri.fromFile(file), ReceiptCrop.FULL)
                fail("Oversized encoded snapshot accepted")
            } catch (_: SelectedImageSnapshotEncoder.ImageInputException) { }
            byteArrayOf(1)
        }
    }

    @Test fun encoderRejectsMainThreadExecution() {
        launch()
        scenario!!.onActivity {
            try { SelectedImageSnapshotEncoder(context.contentResolver).encodeBytes(byteArrayOf(1), ReceiptCrop.FULL); fail("UI image decode accepted") }
            catch (_: IllegalStateException) { }
        }
    }

    @Test fun nonJpegExifIsRejectedRatherThanIgnoringOrientation() {
        val png = image().readBytes()
        val tiff = byteArrayOf(73, 73, 42, 0, 8, 0, 0, 0, 1, 0, 18, 1, 3, 0, 1, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0)
        val pngChunk = java.io.ByteArrayOutputStream().apply {
            val data = java.io.DataOutputStream(this)
            data.writeInt(tiff.size); data.writeBytes("eXIf"); data.write(tiff)
            val crc = java.util.zip.CRC32().apply { update("eXIf".toByteArray()); update(tiff) }
            data.writeInt(crc.value.toInt())
        }.toByteArray()
        val pngExif = png.copyOfRange(0, png.size - 12) + pngChunk + png.copyOfRange(png.size - 12, png.size)
        val bitmap = decode(png)
        @Suppress("DEPRECATION")
        val webp = java.io.ByteArrayOutputStream().also { bitmap.compress(Bitmap.CompressFormat.WEBP, 100, it) }.toByteArray()
        bitmap.recycle()
        val webpExif = webp + "EXIF".toByteArray() + byteArrayOf(26, 0, 0, 0) + tiff
        val riffSize = webpExif.size - 8
        for (i in 0..3) webpExif[4 + i] = (riffSize ushr (8 * i)).toByte()
        worker {
            val encoder = SelectedImageSnapshotEncoder(context.contentResolver)
            // Ordinary inputs still decode; only the unsupported metadata combination fails.
            encoder.encodeBytes(webp, ReceiptCrop.FULL)
            for (source in listOf(pngExif, webpExif)) {
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(source, 0, source.size, bounds)
                assertEquals(100, bounds.outWidth)
                try { encoder.encodeBytes(source, ReceiptCrop.FULL); fail("Unsupported EXIF ignored") }
                catch (_: SelectedImageSnapshotEncoder.ImageInputException) { }
            }
            byteArrayOf(1)
        }
    }

    @Test fun largeSupportedImageIsSampledWithinDecodedAndRetainedLimits() {
        val file = image(width = 3200, height = 1600)
        val bytes = worker { SelectedImageSnapshotEncoder(context.contentResolver).encode(Uri.fromFile(file), ReceiptCrop.FULL) }
        assertTrue(bytes.size <= SelectedImageSnapshotEncoder.MAX_RETAINED_BYTES)
        val bitmap = decode(bytes)
        assertEquals(1600, bitmap.width); assertEquals(800, bitmap.height)
        assertRed(bitmap.getPixel(100, 400)); assertBlue(bitmap.getPixel(1500, 400)); bitmap.recycle()
    }

    @Test fun removedImageIsLocalPreparationErrorAndNeverSyntheticSuccess() {
        val file = image(); gallery(file); assertTrue(file.delete())
        openTest(expectReady = false)
        awaitText(context.getString(R.string.selected_processing_error))
        onView(withId(R.id.selected_processing_start)).check(matches(not(isEnabled())))
        scenario!!.onActivity { assertSame(ReceiptProcessingLifecycle.State.Idle, controller(it).state) }
        onView(withText("Validated synthetic receipt")).check(doesNotExist())
    }

    @Test fun unreadableSelectionDisablesThePreviewAction() {
        val file = File(context.cacheDir, "selected-${UUID.randomUUID()}.png").also { files.add(it); it.writeText("invalid") }
        gallery(file)
        onView(withId(R.id.preview_process_selected)).check(matches(not(isEnabled())))
        onView(withId(R.id.preview_image_error)).check(matches(isDisplayed()))
    }

    @Test fun cancellationAllowsOnlyExplicitRetryWithFreshRequestIdentity() {
        gallery(image()); openTest()
        lateinit var first: ReceiptProcessingRequest
        scenario!!.onActivity { a ->
            controller(a).start(); first = (controller(a).state as ReceiptProcessingLifecycle.State.Pending).request
            controller(a).cancel()
        }
        SystemClock.sleep(700)
        scenario!!.onActivity { assertTrue(controller(it).state is ReceiptProcessingLifecycle.State.Ready) }
        onView(withId(R.id.selected_processing_start)).perform(scrollTo(), click())
        scenario!!.onActivity { a ->
            val next = (controller(a).state as ReceiptProcessingLifecycle.State.Pending).request
            assertSame(first.selection, next.selection); assertNotSame(first.submission, next.submission)
            assertNotEquals(first.context.expectedRequestId, next.context.expectedRequestId)
        }
        awaitText("Validated synthetic receipt")
    }

    @Test fun cropReplacementAfterPendingReleasesOldOwnerAndSnapshot() {
        gallery(image()); openTest()
        lateinit var old: SelectedImageProcessingController
        lateinit var oldSnapshot: ReceiptSubmissionBinding.Snapshot
        scenario!!.onActivity { old = controller(it); oldSnapshot = snapshot(it); old.start() }
        pressBack()
        assertSame(ReceiptProcessingLifecycle.State.Idle, old.state)
        try { oldSnapshot.copyBytes(); fail("Old snapshot retained") } catch (_: IllegalStateException) { }
        crop(ReceiptCrop.from(floatArrayOf(.5f, 0f, 1f, 1f))!!); openTest()
        scenario!!.onActivity {
            assertNotSame(old, controller(it))
            val bitmap = decode(snapshot(it).copyBytes()); assertBlue(bitmap.getPixel(25, 30)); bitmap.recycle()
        }
        SystemClock.sleep(700)
        scenario!!.onActivity { assertTrue(controller(it).state is ReceiptProcessingLifecycle.State.Ready) }
    }

    @Test fun recreationPreparesFreshOwnerWithoutRestoringPendingSubmission() {
        gallery(image()); openTest()
        lateinit var old: SelectedImageProcessingController
        scenario!!.onActivity { old = controller(it); old.start() }
        scenario!!.recreate(); awaitText(context.getString(R.string.selected_processing_ready))
        scenario!!.onActivity { assertNotSame(old, controller(it)); assertTrue(controller(it).state is ReceiptProcessingLifecycle.State.Ready) }
        assertSame(ReceiptProcessingLifecycle.State.Idle, old.state)
    }

    @Test fun backgroundReturnReleasesSnapshotAndDoesNotAutomaticallySubmit() {
        gallery(image()); openTest()
        lateinit var oldSnapshot: ReceiptSubmissionBinding.Snapshot
        scenario!!.onActivity { oldSnapshot = snapshot(it); controller(it).start() }
        scenario!!.moveToState(Lifecycle.State.CREATED)
        try { oldSnapshot.copyBytes(); fail("Snapshot not released on stop") } catch (_: IllegalStateException) { }
        scenario!!.moveToState(Lifecycle.State.RESUMED)
        awaitText(context.getString(R.string.selected_processing_ready))
        SystemClock.sleep(700)
        scenario!!.onActivity { assertTrue(controller(it).state is ReceiptProcessingLifecycle.State.Ready) }
    }

    @Test fun backNavigationCannotBeReopenedByLateWorkAndKeepsManualAndDemoRoutes() {
        gallery(image()); openTest()
        scenario!!.onActivity { controller(it).start() }; pressBack(); SystemClock.sleep(700)
        onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
        onView(withId(R.id.preview_continue)).perform(scrollTo()).check(matches(isEnabled()))
        onView(withId(R.id.preview_remove_image)).perform(scrollTo(), click())
        onView(withId(R.id.preview_continue)).perform(scrollTo()).check(matches(isEnabled()))
    }

    @Test fun selectedPageSupportsPoliteStatusTouchTargetsFocusAndLargeText() {
        val previous = shell("settings get system font_scale").trim().toFloatOrNull() ?: 1f
        try {
            shell("settings put system font_scale 2.0")
            gallery(image()); openTest()
            onView(withId(R.id.selected_processing_start)).perform(scrollTo()).check(matches(isDisplayed()))
            scenario!!.onActivity { a ->
                assertEquals(2f, a.resources.configuration.fontScale, .01f)
                val action = a.findViewById<View>(R.id.selected_processing_prepare_again)
                assertTrue(action.height >= 48 * a.resources.displayMetrics.density)
                assertEquals(View.ACCESSIBILITY_LIVE_REGION_POLITE, a.findViewById<View>(R.id.selected_processing_status).accessibilityLiveRegion)
                action.isFocusableInTouchMode = true; action.requestFocus(); controller(a).start()
                assertEquals(R.id.selected_processing_prepare_again, a.currentFocus?.id)
            }
            awaitText("Validated synthetic receipt")
            onView(withText("0.750")).perform(scrollTo()).check(matches(isDisplayed()))
        } finally { shell("settings put system font_scale $previous") }
    }

    @Test fun automatedReaderProbeRecordsSelectedImageFocusAndOwnerReplacement() {
        gallery(image()); openTest()
        automatedReaderProbe("i2k-selected-accessibility.json") { observe ->
            scenario!!.onActivity { a ->
                val input = a.findViewById<View>(R.id.selected_processing_start)
                input.isFocusableInTouchMode = true; assertTrue(input.requestFocus())
                val reader = a.findViewById<View>(R.id.selected_processing_prepare_again)
                assertTrue(reader.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null))
                assertTrue(input.isFocused); assertTrue(reader.isAccessibilityFocused)
                assertEquals(SelectedImageProcessingController.InputState.READY, controller(a).inputState)
            }
            observe("ready-distinct-input-start-reader-prepare-again")
            scenario!!.onActivity { a ->
                controller(a).start()
                recordProbeFocus(a, "pending-before-corrected-policy-assertions")
                assertTrue(controller(a).state is ReceiptProcessingLifecycle.State.Pending)
                val status = requireNotNull(a.findViewById<View>(R.id.selected_processing_status))
                assertTrue(status.isShown)
                assertNull(a.findViewById<View>(R.id.selected_processing_start))
                assertSame(status, a.currentFocus)
                val reader = requireNotNull(a.findViewById<View>(R.id.selected_processing_prepare_again))
                assertTrue(reader.isEnabled); assertTrue(reader.isShown)
                assertTrue("Surviving reader action must retain independent accessibility focus", reader.isAccessibilityFocused)
                assertOnlyReaderFocus(a, reader)
            }
            observe("pending-after-distinct-focus")
            awaitText("Validated synthetic receipt"); observe("available")
            scenario!!.onActivity { a ->
                val status = a.findViewById<View>(R.id.selected_processing_status)
                assertEquals(View.ACCESSIBILITY_LIVE_REGION_POLITE, status.accessibilityLiveRegion)
                assertTrue(status.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null))
                assertTrue(status.isAccessibilityFocused)
                a.findViewById<View>(R.id.selected_processing_prepare_again).performClick()
                assertEquals(SelectedImageProcessingController.InputState.PREPARING, controller(a).inputState)
            }
            awaitText(context.getString(R.string.selected_processing_ready)); observe("prepared-again-ready")
            scenario!!.onActivity { a -> controller(a).start(); controller(a).cancel() }
            awaitText(context.getString(R.string.selected_processing_ready)); observe("cancelled-ready")
            lateinit var replaced: SelectedImageProcessingController
            scenario!!.onActivity { replaced = controller(it); replaced.start() }
            pressBack(); crop(ReceiptCrop.from(floatArrayOf(.5f, 0f, 1f, 1f))!!); openTest()
            assertSame(ReceiptProcessingLifecycle.State.Idle, replaced.state)
            scenario!!.onActivity { assertNotSame(replaced, controller(it)) }
            observe("replacement-owner-ready")
            lateinit var recreated: SelectedImageProcessingController
            scenario!!.onActivity { recreated = controller(it); recreated.start() }
            scenario!!.recreate(); awaitText(context.getString(R.string.selected_processing_ready))
            assertSame(ReceiptProcessingLifecycle.State.Idle, recreated.state)
            observe("recreated-fresh-ready")
            scenario!!.onActivity { controller(it).start() }
            scenario!!.moveToState(Lifecycle.State.CREATED); scenario!!.moveToState(Lifecycle.State.RESUMED)
            awaitText(context.getString(R.string.selected_processing_ready)); observe("background-fresh-ready")
            pressBack(); onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
            observe("back-preview")
        }
    }


    @Test fun sameControlKeepsBothSelectedImageFocusChannelsThroughCompletion() {
        gallery(image()); openTest()
        automatedReaderProbe("i2k-selected-same-control.json") { observe ->
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_prepare_again)
                controller(a).start()
                recordProbeFocus(a, "same-control-selected-pending")
                assertProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_prepare_again)
            }
            awaitText("Validated synthetic receipt")
            scenario!!.onActivity { a ->
                assertProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_prepare_again)
            }
            observe("same-control-selected-available")
        }
    }

    @Test fun missingOrDisabledSelectedReaderTargetHasNoForcedSubstitute() {
        gallery(image()); openTest()
        automatedReaderProbe("i2k-selected-missing-reader.json") { observe ->
            scenario!!.onActivity { a ->
                val retainedPng = snapshot(a).copyBytes()
                setProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_start)
                controller(a).start()
                recordProbeFocus(a, "selected-reader-start-disappeared")
                assertNull(a.findViewById<View>(R.id.selected_processing_start))
                assertProbeChannels(a, R.id.selected_processing_prepare_again, null)
                controller(a).cancel()
                setProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_start)
                // Exercise PREPARING on the same live controller through its existing API.
                // The separate public Prepare Again action deliberately creates a fresh owner.
                controller(a).prepareInput { retainedPng }
                assertEquals(SelectedImageProcessingController.InputState.PREPARING, controller(a).inputState)
                recordProbeFocus(a, "selected-reader-start-disabled-preparing")
                assertFalse(a.findViewById<View>(R.id.selected_processing_start).isEnabled)
                assertProbeChannels(a, R.id.selected_processing_prepare_again, null)
            }
            awaitText(context.getString(R.string.selected_processing_ready))
            scenario!!.onActivity { assertProbeChannels(it, R.id.selected_processing_prepare_again, null) }
            observe("reenabled-start-does-not-resurrect-old-reader-focus")
        }
    }

    @Test fun selectedRefreshAndOwnerReplacementDoNotInventReaderFocus() {
        gallery(image()); openTest()
        automatedReaderProbe("i2k-selected-no-prior-reader.json") { observe ->
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.selected_processing_prepare_again, null)
                controller(a).start(); assertProbeChannels(a, R.id.selected_processing_prepare_again, null)
                controller(a).cancel(); assertProbeChannels(a, R.id.selected_processing_prepare_again, null)
            }
            observe("selected-start-cancel-with-no-prior-reader")
            lateinit var prepared: SelectedImageProcessingController
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_prepare_again)
                prepared = controller(a)
                a.findViewById<View>(R.id.selected_processing_prepare_again).performClick()
                assertNotSame(prepared, controller(a))
                assertProbeChannels(a, R.id.selected_processing_status, null)
            }
            awaitText(context.getString(R.string.selected_processing_ready))
            assertSame(ReceiptProcessingLifecycle.State.Idle, prepared.state)
            scenario!!.onActivity { assertProbeChannels(it, R.id.selected_processing_status, null) }
            observe("prepare-again-fresh-owner-no-inherited-reader")
            lateinit var stopped: SelectedImageProcessingController
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_prepare_again)
                stopped = controller(a); stopped.start()
            }
            scenario!!.moveToState(Lifecycle.State.CREATED); scenario!!.moveToState(Lifecycle.State.RESUMED)
            awaitText(context.getString(R.string.selected_processing_ready))
            assertSame(ReceiptProcessingLifecycle.State.Idle, stopped.state)
            scenario!!.onActivity { a ->
                assertNotSame(stopped, controller(a)); assertProbeChannels(a, R.id.selected_processing_status, null)
            }
            observe("selected-background-fresh-owner")
            lateinit var recreated: SelectedImageProcessingController
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_prepare_again)
                recreated = controller(a); recreated.start()
            }
            scenario!!.recreate(); awaitText(context.getString(R.string.selected_processing_ready))
            assertSame(ReceiptProcessingLifecycle.State.Idle, recreated.state)
            scenario!!.onActivity { a ->
                assertNotSame(recreated, controller(a)); assertProbeChannels(a, R.id.selected_processing_status, null)
            }
            observe("selected-recreated-fresh-owner")
            lateinit var replaced: SelectedImageProcessingController
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.selected_processing_prepare_again, R.id.selected_processing_prepare_again)
                replaced = controller(a); replaced.start()
            }
            pressBack(); crop(ReceiptCrop.from(floatArrayOf(.5f, 0f, 1f, 1f))!!); openTest()
            assertSame(ReceiptProcessingLifecycle.State.Idle, replaced.state)
            scenario!!.onActivity { a ->
                assertNotSame(replaced, controller(a)); assertProbeChannels(a, R.id.selected_processing_status, null)
            }
            observe("crop-replacement-fresh-owner-no-inherited-reader")
        }
    }


    private fun setProbeChannels(a: MainActivity, inputId: Int, readerId: Int?) {
        fun clear(view: View) {
            if (view.isAccessibilityFocused) assertTrue(view.performAccessibilityAction(
                android.view.accessibility.AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS, null))
            if (view is ViewGroup) for (i in 0 until view.childCount) clear(view.getChildAt(i))
        }
        clear(a.window.decorView)
        val input = requireNotNull(a.findViewById<View>(inputId))
        assertTrue(input.isEnabled); input.isFocusableInTouchMode = true; assertTrue(input.requestFocus())
        val reader = readerId?.let { requireNotNull(a.findViewById<View>(it)) }
        if (reader != null) {
            assertTrue(reader.isEnabled)
            assertTrue(reader.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null))
        }
        assertSame(input, a.currentFocus); assertOnlyReaderFocus(a, reader)
    }

    private fun assertProbeChannels(a: MainActivity, inputId: Int, readerId: Int?) {
        val root = requireNotNull(a.findViewById<View>(R.id.screen_selected_processing))
        assertSame(controller(a), root.tag)
        val input = requireNotNull(root.findViewById<View>(inputId))
        assertTrue(input.isEnabled); assertSame(input, a.currentFocus); assertTrue(input.isFocused)
        val reader = readerId?.let { requireNotNull(root.findViewById<View>(it)) }
        if (reader != null) { assertTrue(reader.isEnabled); assertTrue(reader.isAccessibilityFocused) }
        assertOnlyReaderFocus(a, reader)
    }


    /** Corrected-policy automation service, not a TalkBack speech test. Focus observations are
     * retained before assertions so failed focus restoration has independent evidence. */
    private var probeFocusSnapshots: org.json.JSONArray? = null

    private fun automatedReaderProbe(name: String, block: ((String) -> Unit) -> Unit) {
        val inst = InstrumentationRegistry.getInstrumentation()
        val automation = inst.uiAutomation
        val originalFlags = automation.serviceInfo.flags
        val events = org.json.JSONArray()
        val snapshots = org.json.JSONArray()
        probeFocusSnapshots = snapshots
        val report = org.json.JSONObject().put("service", "UiAutomation; NOT TalkBack")
            .put("manualSpeechVerified", false).put("originalServiceFlags", originalFlags)
            .put("events", events).put("snapshots", snapshots)
        automation.setOnAccessibilityEventListener { event ->
            synchronized(events) {
                if (events.length() < 512) events.put(org.json.JSONObject()
                    .put("type", event.eventType).put("contentChanges", event.contentChangeTypes)
                    .put("window", event.windowId))
            }
        }
        try {
            val info = automation.serviceInfo
            info.flags = originalFlags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_REQUEST_TOUCH_EXPLORATION_MODE
            automation.serviceInfo = info
            val manager = inst.targetContext.getSystemService(android.content.Context.ACCESSIBILITY_SERVICE)
                as android.view.accessibility.AccessibilityManager
            val deadline = SystemClock.uptimeMillis() + 5_000L
            while (!manager.isTouchExplorationEnabled && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(25L)
            assertTrue("Automation touch exploration is actually enabled", manager.isTouchExplorationEnabled)
            report.put("touchExplorationEnabled", true)
            val observe: (String) -> Unit = { stage ->
                inst.waitForIdleSync()
                scenario!!.onActivity { a ->
                    recordProbeFocus(a, stage)
                }
            }
            block(observe)
            report.put("probeCompleted", true)
        } finally {
            automation.setOnAccessibilityEventListener(null)
            val restored = automation.serviceInfo
            restored.flags = originalFlags
            automation.serviceInfo = restored
            report.put("restoredServiceFlags", automation.serviceInfo.flags)
            synchronized(events) {
                inst.targetContext.cacheDir.resolve(name).writeText(report.toString(2))
            }
            probeFocusSnapshots = null
            assertEquals("Automation flags restored", originalFlags, automation.serviceInfo.flags)
        }
    }

    private fun recordProbeFocus(a: MainActivity, stage: String) {
        val readers = org.json.JSONArray()
        fun visit(view: View) {
            if (view.isAccessibilityFocused) readers.put(focusResourceName(a, view))
            if (view is ViewGroup) for (i in 0 until view.childCount) visit(view.getChildAt(i))
        }
        visit(a.window.decorView)
        requireNotNull(probeFocusSnapshots).put(org.json.JSONObject().put("stage", stage)
            .put("inputFocus", focusResourceName(a, a.currentFocus)).put("accessibilityFocus", readers))
    }

    private fun assertOnlyReaderFocus(a: MainActivity, expected: View?) {
        val focused = mutableListOf<View>()
        fun visit(view: View) {
            if (view.isAccessibilityFocused) focused.add(view)
            if (view is ViewGroup) for (i in 0 until view.childCount) visit(view.getChildAt(i))
        }
        visit(a.window.decorView)
        assertEquals(if (expected == null) emptyList<View>() else listOf(expected), focused)
    }

    private fun focusResourceName(a: MainActivity, view: View?): String = when {
        view == null -> "NONE"
        view.id == View.NO_ID -> "NO_ID"
        else -> a.resources.getResourceEntryName(view.id)
    }


    private fun launch() {
        scenario = ActivityScenario.launch(MainActivity::class.java)
        scenario!!.onActivity { a ->
            val state = pantry(a); inventory = state.inventory.toList(); receipt = state.receipt
            presentation = state.presentationResult; confirmed = state.demoConfirmed
        }
    }
    private fun gallery(file: File) {
        launch(); Intents.init(); intents = true
        val action = if (Build.VERSION.SDK_INT >= 33) MediaStore.ACTION_PICK_IMAGES else Intent.ACTION_OPEN_DOCUMENT
        intending(hasAction(action)).respondWith(ActivityResult(Activity.RESULT_OK, Intent().setData(Uri.fromFile(file)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)))
        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
    }
    private fun openTest(expectReady: Boolean = true) {
        onView(withId(R.id.preview_process_selected)).perform(scrollTo(), click())
        if (expectReady) awaitText(context.getString(R.string.selected_processing_ready))
    }
    private fun crop(bounds: ReceiptCrop) {
        onView(withId(R.id.preview_crop_receipt)).perform(scrollTo(), click())
        onView(isAssignableFrom(ReceiptCropView::class.java)).inRoot(isDialog()).perform(object : androidx.test.espresso.ViewAction {
            override fun getConstraints() = isAssignableFrom(ReceiptCropView::class.java)
            override fun getDescription() = "set fictional two-region crop"
            override fun perform(ui: androidx.test.espresso.UiController, view: View) { (view as ReceiptCropView).setCrop(bounds) }
        })
        onView(withText(R.string.crop_apply)).inRoot(isDialog()).perform(scrollTo(), click())
    }
    private fun assertSnapshotRegions() {
        scenario!!.onActivity { a ->
            val snapshot = snapshot(a); val selected = (controller(a).state as ReceiptProcessingLifecycle.State.Ready).selection
            assertSame(selected, snapshot.selection); assertSame(selected.owner, snapshot.owner)
            val bitmap = decode(snapshot.copyBytes()); assertRed(bitmap.getPixel(10, 30)); assertBlue(bitmap.getPixel(90, 30)); bitmap.recycle()
        }
    }
    private fun image(width: Int = 100, height: Int = 60, jpeg: Boolean = false): File {
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = android.graphics.Canvas(bitmap); canvas.drawColor(Color.BLUE)
        canvas.drawRect(0f, 0f, width / 2f, height.toFloat(), android.graphics.Paint().apply { color = Color.RED })
        val file = File(context.cacheDir, "selected-${UUID.randomUUID()}." + if (jpeg) "jpg" else "png")
        file.outputStream().use { bitmap.compress(if (jpeg) Bitmap.CompressFormat.JPEG else Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle(); files.add(file); return file
    }
    private fun orient(file: File, orientation: Int) {
        val jpeg = file.readBytes()
        assertEquals(0xff, jpeg[0].toInt() and 0xff); assertEquals(0xd8, jpeg[1].toInt() and 0xff)
        // Minimal APP1 Exif/TIFF IFD with one SHORT orientation entry. No writer dependency.
        val segment = byteArrayOf(
            0xff.toByte(), 0xe1.toByte(), 0, 34, 69, 120, 105, 102, 0, 0,
            73, 73, 42, 0, 8, 0, 0, 0, 1, 0, 18, 1, 3, 0, 1, 0, 0, 0,
            orientation.toByte(), 0, 0, 0, 0, 0, 0, 0,
        )
        file.writeBytes(jpeg.copyOfRange(0, 2) + segment + jpeg.copyOfRange(2, jpeg.size))
        val original = file.readBytes()
        assertTrue(original.size < 5000) // Exercise the API 26 short-JPEG reader defect.
        file.inputStream().use { assertEquals(orientation, SelectedImageSnapshotEncoder.readOrientation(it)) }
        assertArrayEquals(original, file.readBytes())
    }
    private fun decode(bytes: ByteArray) = requireNotNull(BitmapFactory.decodeByteArray(bytes, 0, bytes.size))
    private fun assertRed(color: Int) { assertTrue(Color.red(color) > 200 && Color.blue(color) < 40) }
    private fun assertBlue(color: Int) { assertTrue(Color.blue(color) > 200 && Color.red(color) < 40) }
    private fun worker(action: () -> ByteArray): ByteArray {
        val worker = Executors.newSingleThreadExecutor()
        return try { worker.submit<ByteArray> { action() }.get(15, TimeUnit.SECONDS) } finally { worker.shutdown() }
    }
    private fun awaitText(text: String) {
        val deadline = SystemClock.uptimeMillis() + 8_000L
        while (SystemClock.uptimeMillis() < deadline) {
            var found = false; scenario!!.onActivity { found = hasText(it.window.decorView, text) }
            if (found) return
            SystemClock.sleep(25)
        }
        fail("Expected selected-image local state")
    }
    private fun hasText(view: View, text: String): Boolean =
        (view is TextView && view.text.toString() == text) ||
            (view is ViewGroup && (0 until view.childCount).any { hasText(view.getChildAt(it), text) })
    private fun controller(a: MainActivity) = MainActivity::class.java.getDeclaredField("selectedProcessingController").apply { isAccessible = true }.get(a) as SelectedImageProcessingController
    private fun snapshot(a: MainActivity): ReceiptSubmissionBinding.Snapshot {
        val transport = SelectedImageProcessingController::class.java.getDeclaredField("transport").apply { isAccessible = true }.get(controller(a))
        return BoundSyntheticReceiptProcessingTransport::class.java.getDeclaredField("snapshot").apply { isAccessible = true }.get(transport) as ReceiptSubmissionBinding.Snapshot
    }
    private fun pantry(a: MainActivity) = MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }.get(a) as PantryUiState
    private fun shell(command: String) = AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(command)).bufferedReader().use { it.readText() }
}
