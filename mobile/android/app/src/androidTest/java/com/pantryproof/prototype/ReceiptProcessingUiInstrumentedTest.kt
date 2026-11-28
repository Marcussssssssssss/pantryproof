package com.pantryproof.prototype

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor.AutoCloseInputStream
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.LinearLayout
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.closeSoftKeyboard
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.*
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle.State
import com.pantryproof.prototype.ui.LiveReceiptReviewDraft
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.ReceiptProcessingUiController
import org.hamcrest.Matchers.containsString
import org.hamcrest.Matchers.equalTo
import org.hamcrest.Matchers.not
import org.hamcrest.Matchers.allOf
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReceiptProcessingUiInstrumentedTest {
    private var scenario: ActivityScenario<MainActivity>? = null
    private var inventory: List<InventoryItem> = emptyList()
    private var receipt: Receipt? = null
    private var presentation: ReceiptPresentationUiResult? = null
    private var confirmation = false

    @After
    fun preservesTheExistingPantryAndClosesThePage() {
        scenario?.onActivity { activity ->
            val pantry = pantry(activity)
            assertEquals(inventory, pantry.inventory)
            assertEquals(receipt, pantry.receipt)
            assertEquals(presentation, pantry.presentationResult)
            assertEquals(confirmation, pantry.demoConfirmed)
        }
        scenario?.close()
    }

    @Test
    fun liveReviewRendersEditsAndSelectionFromAnOfflineFixture() {
        val context = SyntheticReceiptPresentationPayload.context.copy(mode = PresentationConsumerMode.LIVE)
        val payload = SyntheticReceiptPresentationPayload.bytes().decodeToString()
            .replace("SYNTHETIC_FIXTURE", "LOCAL_IMAGE").encodeToByteArray()
        val result = M3eReceiptPresentationAdapter().decodeAndMap(payload, context)
        val request = ReceiptProcessingRequest(
            ReceiptProcessingRequest.Selection(ReceiptProcessingRequest.Owner(), context.expectedImageId),
            ReceiptProcessingRequest.Submission(),
            context,
        )
        val draft = requireNotNull(LiveReceiptReviewDraft.from(
            State.Finished(request, ReceiptProcessingLifecycle.Outcome.Presentation(result)),
        ))
        val originalDescription = draft.items.first().description.value
        launch()
        scenario!!.onActivity { activity ->
            MainActivity::class.java.getDeclaredField("liveReviewDraft").apply { isAccessible = true }
                .set(activity, draft)
            MainActivity::class.java.getDeclaredMethod("renderLiveReceiptReview", LiveReceiptReviewDraft::class.java)
                .apply { isAccessible = true }.invoke(activity, draft)
        }

        onView(withText(R.string.live_review_title)).check(matches(isDisplayed()))
        recordSageScreen("13b-offline-live-review")
        onView(allOf(withText(originalDescription), isAssignableFrom(android.widget.EditText::class.java)))
            .perform(sageScrollTo(), replaceText("Reviewed milk"))
        closeSoftKeyboard()
        val resources = InstrumentationRegistry.getInstrumentation().targetContext.resources
        for (itemNumber in 2..draft.items.size) {
            onView(withText(resources.getString(R.string.live_review_include_item, itemNumber)))
                .perform(scrollTo(), click())
        }
        onView(withText(R.string.live_review_selection_action)).perform(sageScrollTo(), click())
        onView(withText(R.string.live_review_confirm_title)).check(matches(isDisplayed()))
        onView(withText(containsString("Reviewed milk"))).check(matches(isDisplayed()))
        onView(withId(android.R.id.button2)).perform(click())
        scenario!!.onActivity {
            val selection = draft.selection() as LiveReceiptReviewDraft.Selection.Ready
            assertEquals(listOf("Reviewed milk"), selection.rows.map(InventoryItem::name))
        }
    }

    @Test
    fun entryIsReadyWithoutAutomaticSubmission() {
        launch()
        awaitText("Ready for synthetic processing")
        onView(withId(R.id.processing_start)).check(matches(isEnabled()))
        onView(withId(R.id.processing_progress)).check(doesNotExist())
        scenario!!.onActivity { assertTrue(controller(it).state is State.Ready) }
    }

    @Test
    fun idleDisablesSubmissionUntilAnExplicitNewInput() {
        launch()
        scenario!!.onActivity { controller(it).clearSelection() }
        awaitText("No synthetic input selected")
        onView(withId(R.id.processing_start)).check(matches(not(isEnabled())))
        onView(withId(R.id.processing_new_input)).perform(sageScrollTo(), click())
        awaitText("Ready for synthetic processing")
        scenario!!.onActivity { assertTrue(controller(it).state is State.Ready) }
    }

    @Test
    fun availableReceiptShowsExactFieldsAndRowOrderReadOnly() {
        launch()
        start()
        awaitText("Validated synthetic receipt")
        onView(withText("Synthetic Processing Market")).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withText(containsString("Qty: 0.750"))).perform(scrollTo()).check(matches(isDisplayed()))
        screenshot("processing-weighted-fields.png")
        onView(withText("Synthetic rice")).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withText(containsString("Unresolved · Needs review"))).perform(scrollTo()).check(matches(isDisplayed()))
        val optionalPrice = InstrumentationRegistry.getInstrumentation().targetContext.getString(R.string.v4_unit_price_optional)
        onView(withText(containsString(optionalPrice))).perform(sageScrollTo()).check(matches(isDisplayed()))
        recordSageScreen("08-v4-decimal-receipt-details")
        onView(withId(R.id.review_confirm)).check(doesNotExist())
        onView(withId(R.id.review_apply)).check(doesNotExist())
        scenario!!.onActivity {
            val state = controller(it).state as State.Finished
            val available = (state.outcome as ReceiptProcessingLifecycle.Outcome.Presentation).result
                as ReceiptPresentationUiResult.Available
            assertEquals(listOf("weighted", "second"), available.receipt.items.map { row -> row.rowId })
            assertEquals(PresentedFieldStatus.MISSING, available.receipt.items[1].unitPrice.status)
        }
        onView(withId(R.id.processing_scenario)).perform(scrollTo())
        screenshot("processing-available.png")
    }

    @Test
    fun availableResultIdsResolveDistinctHeadingAndSummaryCard() {
        launch()
        start()
        awaitText("Validated synthetic receipt")
        assertProcessingResultIds("available")
        onView(withId(R.id.processing_receipt_heading)).perform(scrollTo())
            .check(matches(withText(R.string.processing_review_title)))
        onView(withId(R.id.processing_receipt)).perform(scrollTo())
            .check(matches(isAssignableFrom(LinearLayout::class.java)))
        onView(withText("Synthetic Processing Market")).check(matches(isDisplayed()))
        onView(withId(R.id.review_confirm)).check(doesNotExist())
        onView(withId(R.id.review_apply)).check(doesNotExist())
    }

    @Test
    fun resultIdsStayUniqueAcrossCancellationReplacementAndRecreation() {
        launch()
        select("No response")
        assertProcessingResultIdsAbsent()
        scenario!!.onActivity { activity ->
            val action = activity.findViewById<View>(R.id.processing_start)
            action.isFocusableInTouchMode = true
            assertTrue(action.requestFocus())
            controller(activity).start()
            assertTrue(controller(activity).state is State.Pending)
            assertSame(activity.findViewById<View>(R.id.processing_status), activity.currentFocus)
        }
        assertProcessingResultIdsAbsent()
        onView(withId(R.id.processing_cancel)).perform(sageScrollTo(), click())
        awaitText("Ready for synthetic processing")
        assertProcessingResultIdsAbsent()
        select("Available receipt")
        start()
        awaitText("Validated synthetic receipt")
        assertProcessingResultIds("before-replacement")
        onView(withId(R.id.processing_new_input)).perform(sageScrollTo(), click())
        awaitText("Ready for synthetic processing")
        assertProcessingResultIdsAbsent()
        select("Available with failed extraction")
        start()
        awaitText("Automatic extraction needs manual review.")
        assertProcessingResultIds("failed-extraction")
        scenario!!.recreate()
        awaitText("Ready for synthetic processing")
        assertProcessingResultIdsAbsent()
        select("Available receipt")
        start()
        awaitText("Validated synthetic receipt")
        assertProcessingResultIds("after-recreation")
        select("Processing unavailable")
        start()
        awaitText("Receipt processing unavailable")
        assertProcessingResultIdsAbsent()
    }

    private fun assertProcessingResultIdsAbsent() {
        scenario!!.onActivity { activity ->
            assertNull(activity.findViewById<View>(R.id.processing_receipt_heading))
            assertNull(activity.findViewById<View>(R.id.processing_receipt))
        }
    }

    private fun assertProcessingResultIds(stage: String) {
        scenario!!.onActivity { activity ->
            val root = requireNotNull(activity.findViewById<View>(R.id.screen_processing_demo))
            assertSame(controller(activity), root.tag)
            val cards = mutableListOf<View>()
            val headings = mutableListOf<View>()
            fun visit(view: View) {
                if (view.id == R.id.processing_receipt) cards.add(view)
                if (view.id == R.id.processing_receipt_heading) headings.add(view)
                if (view is ViewGroup) for (index in 0 until view.childCount) visit(view.getChildAt(index))
            }
            visit(root)
            val card = root.findViewById<View>(R.id.processing_receipt)
            val heading = root.findViewById<View>(R.id.processing_receipt_heading)
            val snapshot = org.json.JSONObject().put("stage", stage)
                .put("cardMatches", cards.size).put("headingMatches", headings.size)
                .put("cardLookupClass", card?.javaClass?.name ?: "ABSENT")
                .put("headingLookupClass", heading?.javaClass?.name ?: "ABSENT")
            activity.cacheDir.resolve("f02-view-id-$stage.json").writeText(snapshot.toString(2))
            assertEquals("Summary card ID must identify exactly one view", 1, cards.size)
            assertEquals("Heading ID must identify exactly one view", 1, headings.size)
            assertTrue("Summary lookup must resolve the card", card is LinearLayout)
            assertTrue("Heading lookup must resolve the heading", heading is TextView)
            assertSame(cards.single(), card)
            assertSame(headings.single(), heading)
            assertNotSame(card, heading)
            assertNotEquals(heading!!.id, card!!.id)
            assertEquals(activity.getString(R.string.processing_review_title), (heading as TextView).text.toString())
            val parent = heading.parent as ViewGroup
            assertSame(parent, card.parent)
            assertTrue(parent.indexOfChild(heading) < parent.indexOfChild(card))
        }
    }

    @Test
    fun failedExtractionShowsExactRb08AnnotationAndNoInventedRows() {
        launch()
        select("Available with failed extraction")
        start()
        awaitText("Automatic extraction needs manual review.")
        onView(withId(R.id.review_extraction_failed_annotation)).check(matches(isDisplayed()))
        onView(withId(R.id.details_item_0)).check(doesNotExist())
        onView(withId(R.id.review_confirm)).check(doesNotExist())
        screenshot("processing-failed-extraction.png")
    }

    @Test
    fun genuineNonAvailableOutcomesRenderDistinctPanels() {
        launch()
        for ((sample, title) in listOf(
            "Processing unavailable" to "Receipt processing unavailable",
            "Processing failed" to "Receipt processing failed",
            "Insufficient evidence" to "Not enough receipt evidence",
        )) {
            select(sample)
            start()
            awaitText(title)
            onView(withId(R.id.details_item_0)).check(doesNotExist())
            onView(withId(R.id.review_confirm)).check(doesNotExist())
        }
    }

    @Test
    fun rejectedBytesAndIdentitiesDisplayTheirStrictCodes() {
        launch()
        for ((sample, code) in listOf(
            "Invalid JSON" to "REJECT_INVALID_JSON",
            "Wrong request identity" to "REJECT_REQUEST_ID_MISMATCH",
            "Wrong image identity" to "REJECT_IMAGE_ID_MISMATCH",
        )) {
            select(sample)
            start()
            awaitText("Receipt presentation rejected")
            onView(withText(containsString(code))).check(matches(isDisplayed()))
            onView(withId(R.id.processing_receipt)).check(doesNotExist())
        }
    }

    @Test
    fun localMissingAndExecutionFailuresHaveSeparateMessages() {
        launch()
        for ((sample, title) in listOf(
            "Missing envelope" to "No presentation was returned",
            "Local execution failure" to "Synthetic execution failed",
        )) {
            select(sample)
            start()
            awaitText(title)
            onView(withId(R.id.details_item_0)).check(doesNotExist())
        }
    }

    @Test
    fun noResponseShowsPendingThenTheDemoDeadlineMessage() {
        launch()
        select("No response")
        start()
        awaitText("Processing synthetic response")
        onView(withId(R.id.processing_progress)).check(matches(isDisplayed()))
        recordSageScreen("10-active-processing")
        onView(withId(R.id.processing_start)).check(doesNotExist())
        awaitText("Synthetic processing timed out", 15_000L)
        recordSageScreen("11-processing-recovery")
    }

    @Test
    fun cancelReturnsToReadyAndAllowsOnlyExplicitRestart() {
        launch()
        select("No response")
        start()
        awaitText("Processing synthetic response")
        onView(withId(R.id.processing_cancel)).perform(sageScrollTo(), click())
        awaitText("Ready for synthetic processing")
        SystemClock.sleep(700L)
        scenario!!.onActivity { assertTrue(controller(it).state is State.Ready) }
    }

    @Test
    fun selectionReplacementWhilePendingDiscardsTheOldSubmission() {
        launch()
        select("No response")
        start()
        select("Available with failed extraction")
        awaitText("Ready for synthetic processing")
        start()
        awaitText("Automatic extraction needs manual review.")
    }

    @Test
    fun backDisposesPendingOwnerWithoutReopeningThePage() {
        launch()
        select("No response")
        start()
        pressBack()
        onView(withId(R.id.screen_development)).check(matches(isDisplayed()))
        SystemClock.sleep(700L)
        onView(withId(R.id.screen_processing_demo)).check(doesNotExist())
        scenario!!.onActivity {
            assertNull(MainActivity::class.java.getDeclaredField("processingController").apply {
                isAccessible = true
            }.get(it))
        }
    }

    @Test
    fun recreationCreatesAFreshReadyOwnerWithoutRestoringPendingWork() {
        launch()
        select("No response")
        start()
        var oldOwner: ReceiptProcessingRequest.Owner? = null
        scenario!!.onActivity { oldOwner = (controller(it).state as State.Pending).request.selection.owner }
        scenario!!.recreate()
        awaitText("Ready for synthetic processing")
        scenario!!.onActivity {
            assertNotSame(oldOwner, (controller(it).state as State.Ready).selection.owner)
        }
    }

    @Test
    fun backgroundReturnCreatesAFreshOwnerAndDoesNotResubmit() {
        launch()
        select("No response")
        start()
        scenario!!.moveToState(Lifecycle.State.CREATED)
        scenario!!.moveToState(Lifecycle.State.RESUMED)
        awaitText("Ready for synthetic processing")
        SystemClock.sleep(700L)
        scenario!!.onActivity { assertTrue(controller(it).state is State.Ready) }
    }

    @Test
    fun statusIsPoliteActionsHaveTouchTargetsAndSurvivingFocusIsKept() {
        launch()
        select("No response")
        scenario!!.onActivity { activity ->
            val action = activity.findViewById<View>(R.id.processing_new_input)
            action.isFocusableInTouchMode = true
            assertTrue(action.requestFocus())
            activity.findViewById<View>(R.id.processing_start).performClick()
            val status = activity.findViewById<View>(R.id.processing_status)
            assertEquals(View.ACCESSIBILITY_LIVE_REGION_POLITE, status.accessibilityLiveRegion)
            assertEquals(R.id.processing_new_input, activity.currentFocus?.id)
        }
        onView(withId(R.id.processing_cancel)).perform(sageScrollTo()).check(matches(isDisplayed()))
        scenario!!.onActivity { activity ->
            val minimum = (48 * activity.resources.displayMetrics.density).toInt()
            assertTrue(activity.findViewById<View>(R.id.processing_cancel).height >= minimum)
        }
    }

    @Test
    fun processingPageRemainsUsableAtTwoHundredPercentFontScale() {
        val original = shell("settings get system font_scale").trim()
        try {
            shell("settings put system font_scale 2.0")
            launch()
            scenario!!.recreate()
            val fontDeadline = SystemClock.uptimeMillis() + 6_000L
            var scaled = false
            while (!scaled && SystemClock.uptimeMillis() < fontDeadline) {
                scenario!!.onActivity { scaled = it.resources.configuration.fontScale >= 1.99f }
                if (!scaled) SystemClock.sleep(50L)
            }
            assertTrue("System font scale reaches 200 percent", scaled)
            awaitText("Ready for synthetic processing")
            onView(withId(R.id.processing_start)).perform(sageScrollTo()).check(matches(isDisplayed()))
            onView(withId(R.id.processing_new_input)).perform(sageScrollTo()).check(matches(isDisplayed()))
            scenario!!.onActivity { assertTrue(it.resources.configuration.fontScale >= 1.99f) }
        } finally {
            shell(if (original == "null") "settings delete system font_scale" else "settings put system font_scale $original")
        }
    }

    @Test fun automatedReaderProbeRecordsIndependentFocusAcrossDemoTransitions() {
        launch(); select("No response")
        automatedReaderProbe("i2k-demo-accessibility.json") { observe ->
            scenario!!.onActivity { a ->
                val input = a.findViewById<View>(R.id.processing_start)
                input.isFocusableInTouchMode = true; assertTrue(input.requestFocus())
                val reader = a.findViewById<View>(R.id.processing_new_input)
                assertTrue(reader.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null))
                assertTrue(input.isFocused); assertTrue(reader.isAccessibilityFocused)
            }
            observe("ready-distinct-input-start-reader-new-input")
            scenario!!.onActivity { a ->
                controller(a).start()
                recordProbeFocus(a, "pending-before-corrected-policy-assertions")
                assertTrue(controller(a).state is State.Pending)
                val status = requireNotNull(a.findViewById<View>(R.id.processing_status))
                assertTrue(status.isShown)
                assertNull(a.findViewById<View>(R.id.processing_start))
                assertSame(status, a.currentFocus)
                val reader = requireNotNull(a.findViewById<View>(R.id.processing_new_input))
                assertTrue(reader.isEnabled); assertTrue(reader.isShown)
                assertTrue("Surviving reader action must retain independent accessibility focus", reader.isAccessibilityFocused)
                assertOnlyReaderFocus(a, reader)
            }
            observe("pending-after-distinct-focus")
            scenario!!.onActivity { a ->
                val status = a.findViewById<View>(R.id.processing_status)
                assertEquals(View.ACCESSIBILITY_LIVE_REGION_POLITE, status.accessibilityLiveRegion)
                assertTrue(status.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null))
                assertTrue(status.isAccessibilityFocused)
                controller(a).cancel()
            }
            awaitText("Ready for synthetic processing"); observe("cancelled-ready")
            scenario!!.onActivity { it.findViewById<View>(R.id.processing_new_input).performClick() }
            observe("new-synthetic-input")
            select("Available receipt"); start(); awaitText("Validated synthetic receipt")
            observe("available")
            select("No response"); start(); awaitText("Synthetic processing timed out", 15_000L)
            observe("timeout")
            scenario!!.onActivity { controller(it).selectInput(); controller(it).start() }
            scenario!!.moveToState(Lifecycle.State.CREATED); scenario!!.moveToState(Lifecycle.State.RESUMED)
            awaitText("Ready for synthetic processing"); observe("background-fresh-ready")
            scenario!!.recreate(); awaitText("Ready for synthetic processing"); observe("recreated-fresh-ready")
            scenario!!.onActivity { controller(it).start() }
            pressBack()
            onView(withId(R.id.screen_development)).check(matches(isDisplayed()))
            observe("back-home")
        }
    }


    @Test fun sameControlKeepsBothFocusChannelsAcrossDemoPendingAndCancel() {
        launch(); select("No response")
        automatedReaderProbe("i2k-demo-same-control.json") { observe ->
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.processing_new_input, R.id.processing_new_input)
                controller(a).start()
                recordProbeFocus(a, "same-control-pending")
                assertProbeChannels(a, R.id.processing_new_input, R.id.processing_new_input)
                controller(a).cancel()
                assertProbeChannels(a, R.id.processing_new_input, R.id.processing_new_input)
            }
            observe("same-control-cancelled-ready")
        }
    }

    @Test fun missingOrDisabledDemoReaderTargetHasNoForcedSubstitute() {
        launch(); select("No response")
        automatedReaderProbe("i2k-demo-missing-reader.json") { observe ->
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.processing_new_input, R.id.processing_start)
                controller(a).start()
                recordProbeFocus(a, "reader-start-disappeared")
                assertNull(a.findViewById<View>(R.id.processing_start))
                assertProbeChannels(a, R.id.processing_new_input, null)
                controller(a).cancel()
                setProbeChannels(a, R.id.processing_new_input, R.id.processing_start)
                controller(a).clearSelection()
                recordProbeFocus(a, "reader-start-disabled-idle")
                assertFalse(a.findViewById<View>(R.id.processing_start).isEnabled)
                assertProbeChannels(a, R.id.processing_new_input, null)
            }
            observe("idle-with-no-forced-reader-substitute")
        }
    }

    @Test fun demoRefreshAndFreshOwnersDoNotInventReaderFocus() {
        launch(); select("No response")
        automatedReaderProbe("i2k-demo-no-prior-reader.json") { observe ->
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.processing_new_input, null)
                controller(a).selectInput()
                assertProbeChannels(a, R.id.processing_new_input, null)
                controller(a).start()
                assertProbeChannels(a, R.id.processing_new_input, null)
                controller(a).cancel()
                assertProbeChannels(a, R.id.processing_new_input, null)
            }
            observe("refresh-start-cancel-with-no-prior-reader")
            lateinit var stopped: ReceiptProcessingUiController
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.processing_new_input, R.id.processing_new_input)
                stopped = controller(a); stopped.start()
            }
            scenario!!.moveToState(Lifecycle.State.CREATED); scenario!!.moveToState(Lifecycle.State.RESUMED)
            awaitText("Ready for synthetic processing")
            assertSame(State.Idle, stopped.state)
            scenario!!.onActivity { a ->
                assertNotSame(stopped, controller(a))
                assertProbeChannels(a, R.id.processing_status, null)
            }
            observe("background-new-owner-has-no-inherited-reader")
            lateinit var recreated: ReceiptProcessingUiController
            scenario!!.onActivity { a ->
                setProbeChannels(a, R.id.processing_new_input, R.id.processing_new_input)
                recreated = controller(a)
            }
            scenario!!.recreate(); awaitText("Ready for synthetic processing")
            assertSame(State.Idle, recreated.state)
            scenario!!.onActivity { a ->
                assertNotSame(recreated, controller(a))
                assertProbeChannels(a, R.id.processing_status, null)
            }
            observe("recreated-owner-has-no-inherited-reader")
            lateinit var leaving: ReceiptProcessingUiController
            scenario!!.onActivity { leaving = controller(it); leaving.start() }
            pressBack(); onView(withId(R.id.screen_development)).check(matches(isDisplayed()))
            assertSame(State.Idle, leaving.state)
            scenario!!.onActivity { assertNull(it.findViewById<View>(R.id.screen_processing_demo)) }
            observe("disposed-owner-back-home")
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
        val root = requireNotNull(a.findViewById<View>(R.id.screen_processing_demo))
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
        scenario!!.onActivity {
            val pantry = pantry(it)
            inventory = pantry.inventory.toList()
            receipt = pantry.receipt
            presentation = pantry.presentationResult
            confirmation = pantry.demoConfirmed
        }
        openSageProcessingDemo()
    }

    private fun start() {
        onView(withId(R.id.processing_start)).perform(sageScrollTo(), click())
    }

    private fun select(label: String) {
        onView(withId(R.id.processing_scenario)).perform(scrollTo(), click())
        onData(equalTo(label)).perform(click())
    }

    private fun awaitText(text: String, maximumMillis: Long = 6_000L) {
        val deadline = SystemClock.uptimeMillis() + maximumMillis
        while (SystemClock.uptimeMillis() < deadline) {
            var found = false
            scenario!!.onActivity { found = hasText(it.window.decorView, text) }
            if (found) return
            SystemClock.sleep(25L)
        }
        fail("Expected synthetic processing status: $text")
    }

    private fun hasText(view: View, text: String): Boolean {
        if (view is TextView && view.text.toString() == text) return true
        if (view is ViewGroup) {
            for (i in 0 until view.childCount) if (hasText(view.getChildAt(i), text)) return true
        }
        return false
    }

    private fun controller(activity: MainActivity) =
        MainActivity::class.java.getDeclaredField("processingController").apply {
            isAccessible = true
        }.get(activity) as ReceiptProcessingUiController

    private fun pantry(activity: MainActivity) =
        MainActivity::class.java.getDeclaredField("state").apply {
            isAccessible = true
        }.get(activity) as PantryUiState

    private fun shell(command: String): String =
        AutoCloseInputStream(InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand(command))
            .bufferedReader().use { it.readText() }

    private fun screenshot(name: String) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        instrumentation.targetContext.cacheDir.resolve(name).outputStream().use {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        bitmap.recycle()
    }
}
