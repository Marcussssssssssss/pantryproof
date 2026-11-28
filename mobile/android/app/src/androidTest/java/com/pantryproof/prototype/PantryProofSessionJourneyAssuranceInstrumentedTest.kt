package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.provider.MediaStore
import android.view.View
import android.view.ViewGroup
import android.widget.DatePicker
import android.widget.EditText
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.UiController
import androidx.test.espresso.ViewAction
import androidx.test.espresso.action.ViewActions.*
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.espresso.matcher.RootMatchers.isDialog
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.*
import com.pantryproof.prototype.image.ReceiptCrop
import com.pantryproof.prototype.image.ReceiptCropView
import com.pantryproof.prototype.ui.InventoryBrowseProjection
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.ReceiptProcessingUiController
import com.pantryproof.prototype.ui.SelectedImageProcessingController
import java.io.File
import java.util.UUID
import java.util.concurrent.atomic.AtomicReference
import org.hamcrest.Matchers.equalTo
import org.hamcrest.Matchers.not
import org.junit.After
import org.junit.Assert.*
import org.hamcrest.Matchers.containsString
import org.junit.Test
import org.junit.runner.RunWith

/** Cross-feature session journeys. All images and responses are fictional; no OCR is invoked. */
@RunWith(AndroidJUnit4::class)
class PantryProofSessionJourneyAssuranceInstrumentedTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private var scenario: ActivityScenario<MainActivity>? = null
    private var intents = false
    private val fixtures = mutableListOf<File>()
    private val galleryInput = AtomicReference<File>()
    private val ownedCaptures = mutableListOf<File>()

    @After
    fun closeTheControlledSessionAndReleaseOnlyItsFixtures() {
        try {
            scenario?.close()
        } finally {
            try { if (intents) Intents.release() } finally {
                (fixtures + ownedCaptures).forEach { file -> if (file.exists()) assertTrue(file.delete()) }
            }
        }
    }

    @Test
    fun independentProcessingThenReviewedDemoAndBrowseRemainSeparate() {
        launch()
        val initial = session()
        onView(withId(R.id.home_add_receipt)).perform(sageScrollTo(), click())
        onView(withId(R.id.screen_add_receipt)).check(matches(isDisplayed()))
        pressBack()
        openSageProcessingDemo()
        onView(withId(R.id.processing_start)).check(matches(isEnabled()))
        scenario!!.onActivity { assertTrue(processing(it).state is ReceiptProcessingLifecycle.State.Ready) }
        onView(withId(R.id.processing_start)).perform(sageScrollTo(), click())
        await { processing(it).state is ReceiptProcessingLifecycle.State.Finished }
        onView(withText("Synthetic Processing Market")).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withText(containsString("Qty: 0.750"))).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withId(R.id.review_confirm)).check(doesNotExist())
        scenario!!.onActivity { assertTrue(hasText(it.window.decorView, context.getString(R.string.processing_demo_body))) }
        assertEquals(initial, session())
        pressBack()

        // The independently reviewed demo receipt is intentionally a separate route.
        pressBack()
        openManualReview()
        onView(withId(R.id.review_store_name)).check(matches(withText("Demo Grocery Store (Synthetic)")))
        field(R.id.review_store_name, "I2E reviewed synthetic store")
        field(R.id.review_item_0_description, "I2E reviewed milk")
        onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
        pressBack()
        onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())
        onView(withId(R.id.review_view_inventory)).perform(sageScrollTo(), click())
        val confirmed = session()
        assertTrue(confirmed.confirmed)
        assertEquals(6, confirmed.inventory.size)
        assertEquals(6, confirmed.inventory.map { it.id }.toSet().size)
        assertEquals("I2E reviewed synthetic store", confirmed.receipt?.storeName)
        val milk = confirmed.inventory.single { it.name == "I2E reviewed milk" }
        assertTrue(milk.id.startsWith("receipt-"))
        browse(" milk ", "Quantity high to low", "Temporary receipt-preview items")
        assertRows(milk.id)
        assertEquals(confirmed, session())
        onView(withTagValue(equalTo("inventory-increase:${milk.id}"))).perform(scrollTo(), click())
        val adjusted = confirmed.copy(inventory = confirmed.inventory.map {
            if (it.id == milk.id) it.copy(quantity = it.quantity + 1.toBigDecimal()) else it
        })
        assertEquals(adjusted, session())
        onView(withText(R.string.inventory_add_receipt)).perform(scrollTo(), click())
        pressBack()
        assertBrowse(" milk ", "Quantity high to low", "Temporary receipt-preview items")
        scenario!!.recreate()
        assertBrowse(" milk ", "Quantity high to low", "Temporary receipt-preview items")
        assertRows(milk.id)
        assertEquals(adjusted, session())
    }

    @Test
    fun galleryCropProcessingThenManualConfirmationUsesOnlyEnteredRows() {
        launch()
        stubGallery(image())
        val initial = session()
        openGalleryFromHome()
        onView(withText(R.string.preview_local_status)).check(matches(isDisplayed()))
        cropLeftHalf()
        prepareSelected()
        scenario!!.onActivity { a ->
            val snap = snapshot(a)
            val selected = (selected(a).state as ReceiptProcessingLifecycle.State.Ready).selection
            assertSame(selected, snap.selection)
            val bitmap = requireNotNull(BitmapFactory.decodeByteArray(snap.copyBytes(), 0, snap.copyBytes().size))
            assertEquals(50, bitmap.width)
            assertEquals(60, bitmap.height)
            assertTrue(Color.red(bitmap.getPixel(25, 30)) > 200)
            bitmap.recycle()
        }
        startSelectedAndAssertFictional()
        assertEquals(initial, session())
        pressBack()
        onView(withId(R.id.preview_continue)).perform(sageScrollTo(), click())
        recordSageScreen("15-manual-entry")
        reviewEnteredValues()
        onView(withText(R.string.manual_confirm_action)).check(doesNotExist())
        assertEquals(initial, session())
        field(R.id.review_store_name, "I2E fictional manual market")
        chooseManualDate()
        field(R.id.review_item_0_description, "I2E manual oats")
        field(R.id.review_item_0_quantity, "2")
        field(R.id.review_item_0_unit_price, "4.00")
        field(R.id.review_item_0_line_total, "8.00")
        field(R.id.review_receipt_total, "8.00")
        reviewEnteredValues()
        onView(withText(R.string.manual_review_title)).check(matches(isDisplayed()))
        recordSageScreen("16-manual-precommit")
        onView(withId(R.id.app_bar_back)).perform(click())
        assertEquals(initial, session())
        reviewEnteredValues()
        onView(withId(R.id.manual_confirm)).perform(click())
        onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
        recordSageScreen("17b-durable-success")
        val admitted = session()
        assertEquals(initial.receipt, admitted.receipt)
        assertEquals(initial.presentation, admitted.presentation)
        assertFalse(admitted.confirmed)
        assertEquals(initial.inventory, admitted.inventory.take(initial.inventory.size))
        val row = admitted.inventory.single { it.id.startsWith(PantryUiState.MANUAL_ROW_PREFIX) }
        assertEquals("I2E manual oats", row.name)
        assertEquals(2.toBigDecimal(), row.quantity)
        assertEquals(initial.inventory.size + 1, admitted.inventory.size)
        browse(" oats ", "Quantity high to low", "Manually entered receipt items")
        assertRows(row.id)
        onView(withText(R.string.manual_inventory_source)).perform(scrollTo()).check(matches(isDisplayed()))
        scenario!!.recreate()
        assertBrowse(" oats ", "Quantity high to low", "Manually entered receipt items")
        assertRows(row.id)
        assertEquals(admitted, session())
    }

    @Test
    fun cameraProcessingAndManualCancellationCleanCaptureWithoutStockAdmission() {
        launch()
        val initial = session()
        val previousCaptureNames = captures().map { it.name }.toSet()
        val fixture = image(jpeg = true)
        Intents.init(); intents = true
        intending(hasAction(MediaStore.ACTION_IMAGE_CAPTURE)).respondWithFunction { intent ->
            @Suppress("DEPRECATION")
            val uri = requireNotNull(intent.getParcelableExtra<Uri>(MediaStore.EXTRA_OUTPUT))
            context.contentResolver.openOutputStream(uri, "w")!!.use { it.write(fixture.readBytes()) }
            ActivityResult(Activity.RESULT_OK, null)
        }
        onView(withId(R.id.home_add_receipt)).perform(sageScrollTo(), click())
        onView(withId(R.id.add_capture_image)).perform(scrollTo(), click())
        onView(withText(R.string.preview_camera_status)).check(matches(isDisplayed()))
        ownedCaptures.addAll(captures().filterNot { it.name in previousCaptureNames })
        assertEquals(1, ownedCaptures.size)
        prepareSelected()
        lateinit var cancelled: ReceiptProcessingRequest
        scenario!!.onActivity { a ->
            val c = selected(a)
            c.start()
            cancelled = (c.state as ReceiptProcessingLifecycle.State.Pending).request
            assertEquals(PresentationConsumerMode.FIXTURE, cancelled.context.mode)
            // Existing UI-owner seam orders cancel before any completion can be admitted.
            a.findViewById<View>(R.id.selected_processing_cancel).performClick()
            assertTrue(c.state is ReceiptProcessingLifecycle.State.Ready)
        }
        onView(withId(R.id.selected_processing_start)).check(matches(isEnabled()))
        assertEquals(initial, session())
        pressBack()
        onView(withId(R.id.preview_continue)).perform(sageScrollTo(), click())
        field(R.id.review_store_name, "Unconfirmed camera draft")
        pressBack()
        onView(withText(R.string.manual_discard_title)).check(matches(isDisplayed()))
        onView(withText(R.string.review_discard_confirm)).perform(click())
        onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
        onView(withId(R.id.preview_remove_image)).perform(scrollTo(), click())
        assertEquals(previousCaptureNames, captures().map { it.name }.toSet())
        onView(withId(R.id.preview_continue)).perform(sageScrollTo(), click())
        onView(withId(R.id.screen_details)).check(matches(isDisplayed()))
        onView(withText("Demo Grocery Store (Synthetic)")).check(matches(isDisplayed()))
        assertEquals(initial, session())
    }

    @Test
    fun confirmedInventorySurvivesPendingRecreationAndImageReplacement() {
        launch()
        confirmAndOpenInventory()
        browse("milk", "Quantity high to low", "Temporary receipt-preview items")
        val confirmed = session()
        val milk = confirmed.inventory.single { it.name == "UHT Milk 1L" && it.id.startsWith("receipt-") }
        onView(withText(R.string.inventory_add_receipt)).perform(scrollTo(), click())
        stubGallery(image())
        onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
        prepareSelected()
        lateinit var oldController: SelectedImageProcessingController
        lateinit var oldSnapshot: ReceiptSubmissionBinding.Snapshot
        lateinit var requestA: ReceiptProcessingRequest
        scenario!!.onActivity { a ->
            oldController = selected(a); oldSnapshot = snapshot(a)
            oldController.start()
            requestA = (oldController.state as ReceiptProcessingLifecycle.State.Pending).request
        }
        scenario!!.recreate()
        await { selected(it).inputState == SelectedImageProcessingController.InputState.READY }
        assertSame(ReceiptProcessingLifecycle.State.Idle, oldController.state)
        assertReleased(oldSnapshot)
        scenario!!.onActivity { assertTrue(selected(it).state is ReceiptProcessingLifecycle.State.Ready) }
        assertEquals(confirmed, session())
        pressBack()
        galleryInput.set(image(left = Color.GREEN))
        onView(withId(R.id.preview_choose_another)).perform(sageScrollTo(), click())
        prepareSelected()
        lateinit var selectionB: ReceiptProcessingRequest.Selection
        scenario!!.onActivity { a ->
            selectionB = (selected(a).state as ReceiptProcessingLifecycle.State.Ready).selection
            assertNotSame(requestA.selection, selectionB)
            assertNotSame(requestA.selection.owner, selectionB.owner)
            assertNotEquals(requestA.context.expectedImageId, selectionB.imageId)
            val bytes = snapshot(a).copyBytes()
            val bitmap = requireNotNull(BitmapFactory.decodeByteArray(bytes, 0, bytes.size))
            assertTrue(Color.green(bitmap.getPixel(10, 30)) > 200)
            bitmap.recycle()
        }
        startSelectedAndAssertFictional()
        scenario!!.onActivity { a ->
            val final = selected(a).state as ReceiptProcessingLifecycle.State.Finished
            assertSame(selectionB, final.request.selection)
            assertNotEquals(requestA.context.expectedRequestId, final.request.context.expectedRequestId)
        }
        assertEquals(confirmed, session())
        pressBack()
        pressBack()
        onView(withId(R.id.screen_add_receipt)).check(doesNotExist())
        onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
        assertBrowse("milk", "Quantity high to low", "Temporary receipt-preview items")
        assertRows(milk.id)
        assertEquals(confirmed, session())
        scenario!!.recreate()
        assertEquals(confirmed, session())
        assertRows(milk.id)
    }

    private data class Session(
        val receipt: Receipt?, val presentation: ReceiptPresentationUiResult,
        val inventory: List<InventoryItem>, val confirmed: Boolean,
    )

    private fun launch() { scenario = ActivityScenario.launch(MainActivity::class.java) }
    private fun session(): Session {
        lateinit var value: Session
        scenario!!.onActivity { a ->
            val p = pantry(a)
            value = Session(p.receipt, p.presentationResult, p.inventory.toList(), p.demoConfirmed)
        }
        return value
    }

    private fun stubGallery(file: File) {
        galleryInput.set(file)
        Intents.init(); intents = true
        val action = if (Build.VERSION.SDK_INT >= 33) MediaStore.ACTION_PICK_IMAGES else Intent.ACTION_OPEN_DOCUMENT
        intending(hasAction(action)).respondWithFunction {
            ActivityResult(Activity.RESULT_OK, Intent().setData(Uri.fromFile(galleryInput.get())).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
        }
    }

    private fun openGalleryFromHome() {
        onView(withId(R.id.home_add_receipt)).perform(sageScrollTo(), click())
        onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
    }

    private fun prepareSelected() {
        onView(withId(R.id.preview_process_selected)).perform(sageScrollTo(), click())
        await { selected(it).inputState == SelectedImageProcessingController.InputState.READY }
        onView(withId(R.id.selected_processing_start)).check(matches(isEnabled()))
        scenario!!.onActivity { assertTrue(selected(it).state is ReceiptProcessingLifecycle.State.Ready) }
    }

    private fun startSelectedAndAssertFictional() {
        onView(withId(R.id.selected_processing_start)).perform(sageScrollTo(), click())
        await { selected(it).state is ReceiptProcessingLifecycle.State.Finished }
        onView(withText("Synthetic Processing Market")).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withText(containsString("Qty: 0.750"))).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withId(R.id.review_apply)).check(doesNotExist())
        onView(withId(R.id.review_confirm)).check(doesNotExist())
        scenario!!.onActivity { a ->
            assertTrue(hasText(a.window.decorView, context.getString(R.string.selected_processing_fictional)))
            val state = selected(a).state as ReceiptProcessingLifecycle.State.Finished
            assertEquals(PresentationConsumerMode.FIXTURE, state.request.context.mode)
            assertTrue((state.outcome as ReceiptProcessingLifecycle.Outcome.Presentation).result is ReceiptPresentationUiResult.Available)
        }
    }

    private fun field(id: Int, value: String) {
        // Move input focus as a user would. replaceText alone leaves the invalid
        // store field focused, allowing its scroll requests to race later actions.
        onView(withId(id)).perform(sageScrollTo(), click(), replaceText(value), closeSoftKeyboard())
        onView(withId(id)).check(matches(withText(value)))
        onView(withId(id)).check(matches(hasFocus()))
    }

    private fun chooseManualDate() {
        onView(withId(R.id.manual_calendar)).perform(sageScrollTo(), click())
        onView(isAssignableFrom(DatePicker::class.java)).perform(object : ViewAction {
            override fun getConstraints() = isAssignableFrom(DatePicker::class.java)
            override fun getDescription() = "choose a fictional session receipt date"
            override fun perform(ui: UiController, view: View) {
                (view as DatePicker).updateDate(2026, 10, 10)
                ui.loopMainThreadUntilIdle()
            }
        })
        onView(withId(android.R.id.button1)).perform(click())
        onView(withId(R.id.review_purchase_date)).check(matches(withText("10-11-2026")))
    }

    private fun reviewEnteredValues() {
        val deadline = SystemClock.uptimeMillis() + 5_000L
        while (SystemClock.uptimeMillis() < deadline) {
            // Validation feedback changes form height. Scroll again after pending layout,
            // and keep Espresso's real click/visibility constraints rather than bypassing them.
            onView(withId(R.id.manual_review_action)).perform(sageScrollTo())
            var visible = false
            scenario!!.onActivity { a ->
                val action = a.findViewById<View>(R.id.manual_review_action)
                val rectangle = Rect()
                visible = !action.isLayoutRequested && action.getGlobalVisibleRect(rectangle) &&
                    rectangle.height() >= action.height * .9f && rectangle.width() >= action.width * .9f
            }
            if (visible) {
                onView(withId(R.id.manual_review_action)).perform(click())
                return
            }
            SystemClock.sleep(25L)
        }
        fail("Manual review action did not become reachable after validation layout")
    }

    private fun cropLeftHalf() {
        onView(withId(R.id.preview_crop_receipt)).perform(scrollTo(), click())
        onView(isAssignableFrom(ReceiptCropView::class.java)).inRoot(isDialog()).perform(object : ViewAction {
            override fun getConstraints() = isAssignableFrom(ReceiptCropView::class.java)
            override fun getDescription() = "select the generated image's red half"
            override fun perform(ui: UiController, view: View) {
                (view as ReceiptCropView).setCrop(requireNotNull(ReceiptCrop.from(floatArrayOf(0f, 0f, .5f, 1f))))
            }
        })
        onView(withId(R.id.crop_apply_action)).inRoot(isDialog()).perform(click())
    }

    private fun browse(query: String, sort: String, filter: String) {
        field(R.id.inventory_search, query)
        selectInventorySort(sort)
        selectInventoryFilter(filter)
    }

    private fun choose(id: Int, label: String) {
        onView(withId(id)).perform(scrollTo(), click())
        onData(equalTo(label)).perform(click())
    }

    private fun assertBrowse(query: String, sort: String, filter: String) {
        onView(withId(R.id.inventory_search)).check(matches(withText(query)))
        scenario!!.onActivity { a ->
            assertEquals(sort, ViewCompat.getStateDescription(a.findViewById<View>(R.id.inventory_sort))?.toString())
            val index = a.resources.getStringArray(R.array.inventory_filter_options).indexOf(filter)
            val option = a.resources.getStringArray(R.array.sage_inventory_filter_labels)[index]
            val control = a.findViewById<View>(R.id.inventory_filter)
            assertEquals(index != 0, control.isSelected)
            assertEquals(option, ViewCompat.getStateDescription(control).toString())
        }
    }

    private fun assertRows(vararg ids: String) {
        scenario!!.onActivity { a ->
            val rows = a.findViewById<ViewGroup>(R.id.inventory_browse_results)
            fun collect(view: View): List<String> = (view.tag as? String)?.let(::listOf)
                ?: if (view is ViewGroup) (0 until view.childCount).flatMap { collect(view.getChildAt(it)) }
                else emptyList()
            assertEquals(ids.toList(), collect(rows))
        }
    }

    private fun await(condition: (MainActivity) -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + 10_000L
        while (SystemClock.uptimeMillis() < deadline) {
            var ready = false
            scenario!!.onActivity { ready = condition(it) }
            if (ready) return
            SystemClock.sleep(25L) // Bounded condition polling, matching existing instrumentation helpers.
        }
        fail("Expected Android session transition did not arrive")
    }

    private fun image(jpeg: Boolean = false, left: Int = Color.RED): File {
        val bitmap = Bitmap.createBitmap(100, 60, Bitmap.Config.ARGB_8888)
        Canvas(bitmap).apply {
            drawColor(Color.BLUE)
            drawRect(0f, 0f, 50f, 60f, Paint().apply { color = left })
        }
        val file = File(context.cacheDir, "i2e-synthetic-${UUID.randomUUID()}.${if (jpeg) "jpg" else "png"}")
        file.outputStream().use { assertTrue(bitmap.compress(if (jpeg) Bitmap.CompressFormat.JPEG else Bitmap.CompressFormat.PNG, 100, it)) }
        bitmap.recycle()
        fixtures.add(file)
        return file
    }

    private fun captures() = File(context.cacheDir, "receipt_camera").listFiles().orEmpty().toList()
    private fun pantry(a: MainActivity) = MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }.get(a) as PantryUiState
    private fun processing(a: MainActivity) = MainActivity::class.java.getDeclaredField("processingController").apply { isAccessible = true }.get(a) as ReceiptProcessingUiController
    private fun selected(a: MainActivity) = MainActivity::class.java.getDeclaredField("selectedProcessingController").apply { isAccessible = true }.get(a) as SelectedImageProcessingController
    private fun snapshot(a: MainActivity) = selectedImageSnapshot(selected(a))

    private fun assertReleased(snapshot: ReceiptSubmissionBinding.Snapshot) {
        try { snapshot.copyBytes(); fail("Disposed image snapshot must be released") } catch (_: IllegalStateException) { }
    }

    private fun hasText(view: View, text: String): Boolean = (view is TextView && view.text.toString() == text) ||
        (view is ViewGroup && (0 until view.childCount).any { hasText(view.getChildAt(it), text) })
}
