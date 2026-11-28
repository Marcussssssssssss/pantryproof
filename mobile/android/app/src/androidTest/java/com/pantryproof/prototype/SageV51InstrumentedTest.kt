package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.provider.MediaStore
import android.text.InputType
import android.view.KeyEvent
import android.view.View
import android.view.accessibility.AccessibilityManager
import android.widget.EditText
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.closeSoftKeyboard
import androidx.test.espresso.action.ViewActions.pressKey
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isEnabled
import androidx.test.espresso.matcher.ViewMatchers.withContentDescription
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withTagValue
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.ui.EditableReceipt
import org.hamcrest.Matchers.containsString
import org.hamcrest.Matchers.equalTo
import org.hamcrest.Matchers.not
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class SageV51InstrumentedTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private val compact get() = InstrumentationRegistry.getArguments().getString("v4Compact") == "true"

    @Test fun manualFormFormatsAndRestoresDateAndReviewsTheCurrentDraft() = withManualForm { scenario ->
        onView(withText(R.string.manual_cancel_action)).check(doesNotExist())
        onView(withText("Items (1)")).check(matches(isDisplayed()))
        edit(R.id.review_store_name, "Fictional Market")
        edit(R.id.review_purchase_date, "0102202")
        onView(withText(R.string.v51_date_incomplete)).check(doesNotExist())
        scenario.recreate()
        onView(withId(R.id.review_purchase_date)).check(matches(withText("01-02-202")))
        onView(withId(R.id.manual_review_action)).perform(click())
        onView(withText(R.string.v51_date_incomplete)).check(matches(isDisplayed()))
        onView(withId(R.id.screen_manual_review)).check(doesNotExist())

        edit(R.id.review_purchase_date, "29022026")
        onView(withText(R.string.v51_date_invalid)).check(matches(isDisplayed()))
        recordSageScreen("08-v51-invalid-date")
        val date = onView(withId(R.id.review_purchase_date))
        date.perform(sageScrollTo(), click(), replaceText("010220269"))
        date.check(matches(withText("01-02-2026")))
        date.check { view, missing ->
            if (missing != null) throw missing
            val field = view as EditText
            assertEquals(InputType.TYPE_CLASS_NUMBER, field.inputType and InputType.TYPE_MASK_CLASS)
            assertTrue(field.createAccessibilityNodeInfo().isEditable)
        }
        recordSageScreen("07-v51-date-keyboard")
        date.perform(closeSoftKeyboard())
        scenario.onActivity { activity ->
            val field = activity.findViewById<EditText>(R.id.review_purchase_date)
            field.setSelection(1, 2)
            field.text.replace(1, 2, "3")
            assertEquals("03-02-2026", field.text.toString())
            field.setSelection(field.length())
            assertEquals(10, field.selectionStart)
            val draft = MainActivity::class.java.getDeclaredField("manualDraft").apply { isAccessible = true }
                .get(activity) as EditableReceipt
            assertEquals("2026-02-03", draft.purchaseDate)
        }
        edit(R.id.review_item_0_description, "Fictional oats")
        edit(R.id.review_item_0_quantity, "2")
        edit(R.id.review_item_0_line_total, "8.00")
        edit(R.id.review_receipt_total, "8.00")
        recordSageScreen("05-v51-expanded-fields")
        val add = onView(withId(R.id.manual_add_item))
        add.perform(sageScrollTo(), click()).check(matches(withContentDescription(R.string.manual_add_item)))
        onView(withText("Items (2)")).perform(sageScrollTo()).check(matches(isDisplayed()))
        recordSageScreen("04-v51-add-item")
        onView(withId(R.id.review_item_1_description)).perform(sageScrollTo()).check(matches(isDisplayed()))
        onView(withId(R.id.review_item_0_description)).check(matches(withText("Fictional oats")))
        onView(withText(context.getString(R.string.manual_remove_item, 2))).perform(sageScrollTo(), click())
        onView(withText(R.string.manual_remove_confirm_action)).perform(click())
        onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click())
        onView(withText("Fictional Market · 03-02-2026")).check(matches(isDisplayed()))
        onView(withText("Qty: 2 · RM 8.00")).check(matches(isDisplayed()))
        recordSageScreen("06-v51-collapsed-summary")
        onView(withId(R.id.manual_review_action)).perform(click())
        onView(withId(R.id.screen_manual_review)).check(matches(isDisplayed()))
        onView(withId(R.id.manual_confirm)).check(matches(withText(R.string.v51_confirm_receipt)))
        onView(withText(containsString("Unit price not provided"))).perform(sageScrollTo()).check(matches(isDisplayed()))
        recordSageScreen("09-v51-clean-review")
        pressBack()
        onView(withId(R.id.screen_manual)).check(matches(isDisplayed()))
        onView(withId(R.id.review_store_name)).check(matches(withText("Fictional Market")))
        onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click())
        edit(R.id.review_item_0_unit_price, "4.01")
        edit(R.id.review_receipt_total, "8.01")
        onView(withId(R.id.manual_review_action)).perform(click())
        onView(withText("1 price difference")).check(matches(isDisplayed()))
        onView(withText(R.string.v51_total_difference)).perform(sageScrollTo()).check(matches(isDisplayed()))
        onView(withText("Calculated RM 8.02 · Entered RM 8.00")).perform(sageScrollTo()).check(matches(isDisplayed()))
        onView(withId(R.id.manual_confirm)).check(matches(withText(R.string.manual_confirm_action)))
        recordSageScreen("10-v51-discrepancy-review")
        val store = ManualInventoryStore(context)
        assertTrue(requireNotNull(store.load()).isEmpty())
        onView(withId(R.id.manual_confirm)).perform(click())
        onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
        onView(withText(R.string.sage_receipt_confirmed)).check(matches(isDisplayed()))
        assertEquals("Fictional oats", requireNotNull(store.load()).single().name)
        assertEquals(2.toBigDecimal(), requireNotNull(store.load()).single().quantity)
        recordSageScreen("11-v51-receipt-success")
        onView(withId(R.id.inventory_success_dismiss)).perform(click())
        onView(withId(R.id.inventory_success)).check(doesNotExist())
    }

    @Test fun compactBrandAndManualPricesRemainReachable() = withManualForm { scenario ->
        edit(R.id.review_store_name, "Fictional Market")
        edit(R.id.review_purchase_date, "29022024")
        scenario.onActivity { activity ->
            val unit = activity.findViewById<View>(R.id.review_item_0_unit_price)
            val line = activity.findViewById<View>(R.id.review_item_0_line_total)
            if (compact) {
                assertTrue(activity.resources.configuration.screenWidthDp <= 320)
                assertEquals(2f, unit.resources.configuration.fontScale, .01f)
                val a = IntArray(2).also(unit::getLocationOnScreen)
                val b = IntArray(2).also(line::getLocationOnScreen)
                assertEquals(a[0], b[0])
                assertTrue(b[1] > a[1])
            }
        }
        onView(withId(R.id.review_item_0_unit_price)).perform(sageScrollTo()).check(matches(isDisplayed()))
        onView(withId(R.id.manual_review_action)).check(matches(isDisplayed()))
        recordSageScreen("14-v51-large-manual")
        onView(withId(R.id.app_bar_back)).perform(click())
        onView(withText(R.string.review_keep_editing)).perform(click())
        onView(withId(R.id.review_purchase_date)).check(matches(withText("29-02-2024")))
        pressBack()
        onView(withText(R.string.review_discard_confirm)).perform(click())
        onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
        pressBack()
        onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
        assertTrue(requireNotNull(ManualInventoryStore(context).load()).isEmpty())
    }

    @Test fun rowDismissalRestoresTouchAppearanceAndFeedbackOnlyFollowsSuccess() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            if (compact) scenario.onActivity { enlargeSageTestText(it); refreshInventoryFixture(it) }
            onView(withId(R.id.pantry_brand_logo)).check { view, missing ->
                if (missing != null) throw missing
                val logo = view
                assertTrue(logo.clipToOutline)
                assertEquals(38f, logo.width / logo.resources.displayMetrics.density, 1f)
            }
            recordSageScreen(if (compact) "14b-v51-large-brand" else "01-v51-brand")
            onView(withId(R.id.inventory_add_item)).perform(click())
            onView(withId(R.id.inventory_item_name)).perform(replaceText("Fictional oats"), closeSoftKeyboard())
            onView(withId(R.id.inventory_item_quantity)).perform(replaceText("3"), closeSoftKeyboard())
            onView(withId(android.R.id.button1)).perform(click())
            onView(withText(R.string.v51_item_added)).check(matches(isDisplayed()))
            onView(withId(R.id.inventory_success_dismiss)).perform(click())
            val id = requireNotNull(ManualInventoryStore(context).load()).single().id
            selectInventorySort("Product name A–Z")
            val row = onView(withTagValue(equalTo(id)))
            fun normalRow() {
                row.perform(sageScrollTo()).check { view, missing ->
                    if (missing != null) throw missing
                    assertFalse(view.isSelected || view.isActivated || view.isPressed || view.isFocusableInTouchMode)
                    assertTrue(view.isFocusable && view.isEnabled)
                    assertEquals(1f, view.alpha, 0f)
                }
            }
            normalRow()
            recordSageScreen("12-v51-row-before")
            row.perform(click())
            onView(withContentDescription(R.string.sage_close)).perform(click())
            normalRow()
            recordSageScreen("13-v51-row-after")
            row.perform(click())
            pressBack()
            normalRow()
            row.perform(click())
            val sheet = onView(withId(R.id.sage_inventory_details))
            sheet.check(matches(isDisplayed()))
            // Tap the status-bar side of the dimmed activity, outside the existing floating sheet.
            android.os.ParcelFileDescriptor.AutoCloseInputStream(
                instrumentation.uiAutomation.executeShellCommand("input tap 20 120"),
            ).use { it.readBytes() }
            instrumentation.waitForIdleSync()
            sheet.check(doesNotExist())
            normalRow()

            row.perform(click())
            onView(withTagValue(equalTo("inventory-increase:" + id))).perform(sageScrollTo(), click())
            pressBack()
            onView(withText(R.string.v51_quantity_updated)).check(matches(isDisplayed()))
            normalRow()
            row.perform(click())
            onView(withTagValue(equalTo("inventory-edit:" + id))).perform(sageScrollTo(), click())
            onView(withContentDescription(R.string.sage_close)).perform(click())
            onView(withId(R.id.sage_inventory_details)).check(matches(isDisplayed()))
            onView(withTagValue(equalTo("inventory-edit:" + id))).perform(sageScrollTo(), click())
            onView(withId(R.id.inventory_item_name)).perform(replaceText("Fictional rice"), closeSoftKeyboard())
            onView(withId(android.R.id.button1)).perform(click())
            onView(withText(R.string.v51_changes_saved)).check(matches(isDisplayed()))
            onView(withText(R.string.v51_quantity_updated)).check(doesNotExist())
            normalRow()
            row.perform(click())
            onView(withTagValue(equalTo("inventory-delete:" + id))).perform(sageScrollTo(), click())
            onView(withId(android.R.id.button2)).perform(click())
            pressBack()
            normalRow()
            row.perform(click())
            onView(withTagValue(equalTo("inventory-delete:" + id))).perform(sageScrollTo(), click())
            onView(withId(android.R.id.button1)).perform(click())
            onView(withText(R.string.v51_item_removed)).check(matches(isDisplayed()))
            assertTrue(requireNotNull(ManualInventoryStore(context).load()).isEmpty())
            val duration = if (Build.VERSION.SDK_INT >= 29)
                context.getSystemService(AccessibilityManager::class.java)!!.getRecommendedTimeoutMillis(5_000, 7)
                else 5_000
            SystemClock.sleep(duration.toLong() + 250)
            onView(withId(R.id.inventory_success)).check(doesNotExist())
        }
    }

    @Test fun keyboardActivatedRowRetainsItsRealFocusAfterSheetDismissal() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            selectInventorySort("Product name A–Z")
            instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_DOWN)
            val tag = "stock-rice"
            scenario.onActivity {
                val row = it.findViewById<View>(R.id.inventory_browse_results).findViewWithTag<View>(tag)
                assertFalse(row.isInTouchMode)
                assertTrue(row.requestFocus())
                assertTrue(row.performClick())
            }
            onView(withId(R.id.sage_inventory_details)).check(matches(isDisplayed()))
            pressBack()
            onView(withTagValue(equalTo(tag))).check { view, missing ->
                if (missing != null) throw missing
                assertTrue(view.isFocused)
                assertFalse(view.isFocusableInTouchMode)
                assertEquals("android.widget.Button", view.createAccessibilityNodeInfo().className.toString())
            }
        }
    }

    @Test fun v52FutureDateReviewAndFinalWriteUseTheLocalDay() = withManualForm { scenario ->
        val current = java.time.LocalDate.now()
        var today = current
        val store = ManualInventoryStore(context)
        scenario.onActivity { activity ->
            val state = com.pantryproof.prototype.ui.PantryUiState(
                com.pantryproof.prototype.data.MockReceiptPresentationSource(), store, today = { today },
            )
            MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }.set(activity, state)
        }
        val formatter = com.pantryproof.prototype.ui.PurchaseDateInput
        val date = onView(withId(R.id.review_purchase_date))
        edit(R.id.review_store_name, "Fictional Market")
        edit(R.id.review_item_0_description, "Fictional oats")
        edit(R.id.review_item_0_quantity, "2")
        edit(R.id.review_item_0_unit_price, "4.01")
        edit(R.id.review_item_0_line_total, "8.00")
        edit(R.id.review_receipt_total, "8.00")

        val tomorrow = formatter.display(current.plusDays(1))
        date.perform(sageScrollTo(), click(),
            androidx.test.espresso.action.ViewActions.typeText(tomorrow.replace("-", "")), closeSoftKeyboard())
        date.check(matches(withText(tomorrow)))
        onView(withText(R.string.purchase_date_future)).check(matches(isDisplayed()))
        recordSageScreen("07-v52-future-date")

        val nextYear = formatter.display(current.plusYears(1))
        scenario.onActivity { activity ->
            val field = activity.findViewById<EditText>(R.id.review_purchase_date)
            val clipboard = activity.getSystemService(android.content.ClipboardManager::class.java)!!
            clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Fictional date", nextYear))
            field.selectAll()
            assertTrue(field.onTextContextMenuItem(android.R.id.paste))
            if (Build.VERSION.SDK_INT >= 28) clipboard.clearPrimaryClip()
        }
        date.check(matches(withText(nextYear)))
        onView(withText(R.string.purchase_date_future)).check(matches(isDisplayed()))

        onView(withId(R.id.manual_calendar)).perform(sageScrollTo(), click())
        onView(androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom(android.widget.DatePicker::class.java))
            .check { view, missing ->
                if (missing != null) throw missing
                val picker = view as android.widget.DatePicker
                val calendar = java.util.Calendar.getInstance().apply { timeInMillis = picker.maxDate }
                assertEquals(current, java.time.LocalDate.of(calendar.get(java.util.Calendar.YEAR),
                    calendar.get(java.util.Calendar.MONTH) + 1, calendar.get(java.util.Calendar.DAY_OF_MONTH)))
                assertEquals(current, java.time.LocalDate.of(picker.year, picker.month + 1, picker.dayOfMonth))
            }
        val future = current.plusDays(1)
        val dayLabel = future.format(java.time.format.DateTimeFormatter.ofPattern("dd MMMM uuuu"))
        fun findDay(node: android.view.accessibility.AccessibilityNodeInfo): android.view.accessibility.AccessibilityNodeInfo? {
            if (node.contentDescription?.toString() == dayLabel) return node
            for (index in 0 until node.childCount) {
                node.getChild(index)?.let { findDay(it) }?.let { return it }
            }
            return null
        }
        val tomorrowCell = instrumentation.uiAutomation.rootInActiveWindow?.let(::findDay)
        if (tomorrowCell != null) {
            assertFalse(tomorrowCell.isEnabled)
            val bounds = android.graphics.Rect().also(tomorrowCell::getBoundsInScreen)
            if (!bounds.isEmpty) {
                android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(
                    "input tap " + bounds.centerX() + " " + bounds.centerY(),
                )).use { it.readBytes() }
            }
        }
        onView(androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom(android.widget.DatePicker::class.java))
            .check { view, missing ->
                if (missing != null) throw missing
                val picker = view as android.widget.DatePicker
                assertEquals(current, java.time.LocalDate.of(picker.year, picker.month + 1, picker.dayOfMonth))
            }
        recordSageScreen("08-v52-calendar-maximum")
        pressBack()
        date.check(matches(withText(nextYear)))
        onView(withText(R.string.details_summary_title)).perform(sageScrollTo(), click())
        onView(withId(R.id.manual_review_action)).perform(click())
        onView(withId(R.id.screen_manual_review)).check(doesNotExist())
        date.check(matches(isDisplayed()))
        assertTrue(requireNotNull(store.load()).isEmpty())
        recordSageScreen("09-v52-future-review-refusal")

        edit(R.id.review_purchase_date, formatter.display(current))
        onView(withText(R.string.purchase_date_future)).check(doesNotExist())
        date.perform(sageScrollTo())
        recordSageScreen("06-v52-current-date")
        onView(withId(R.id.manual_review_action)).perform(click())
        onView(withId(R.id.manual_confirm)).check(matches(withText(R.string.manual_confirm_action)))
        today = current.minusDays(1)
        onView(withId(R.id.manual_confirm)).perform(click())
        onView(withText(R.string.purchase_date_future)).check(matches(isDisplayed()))
        onView(withId(R.id.manual_confirm)).check(matches(not(isEnabled())))
        assertTrue(requireNotNull(store.load()).isEmpty())
        recordSageScreen("09b-v52-final-confirmation-refusal")

        onView(withId(R.id.app_bar_back)).perform(click())
        edit(R.id.review_purchase_date, formatter.display(today))
        onView(withId(R.id.manual_review_action)).perform(click())
        onView(withText(formatter.display(today))).check(matches(isDisplayed()))
        recordSageScreen("10-v52-valid-review")
        onView(withId(R.id.manual_confirm)).perform(click())
        onView(withText(R.string.sage_receipt_confirmed)).check(matches(isDisplayed()))
        assertEquals(2.toBigDecimal(), requireNotNull(store.load()).single().quantity)
        recordSageScreen("10b-v52-valid-confirmation")
    }

    @Test fun v52InventoryTouchUsesLightBackgroundWithoutFadingContent() {
        ActivityScenario.launch(MainActivity::class.java).use {
            val demo = onView(withText("Demo inventory"))
            recordSageScreen("01-v52-collapsed")
            heldInventoryTouch(demo, "02-v52-group-pressed")
            onView(withText("Jasmine Rice 5kg")).check(matches(isDisplayed()))
            recordSageScreen("03-v52-expanded")
            demo.perform(click(), click(), click())
            onView(withText("Jasmine Rice 5kg")).check(matches(not(isDisplayed())))
            demo.perform(click())
            val row = onView(withTagValue(equalTo("stock-rice")))
            row.perform(sageScrollTo())
            recordSageScreen("04-v52-row-before")
            heldInventoryTouch(row, "04b-v52-row-pressed")
            onView(withId(R.id.sage_inventory_details)).check(matches(isDisplayed()))
            pressBack()
            row.check { view, missing ->
                if (missing != null) throw missing
                assertFalse(view.isPressed || view.isSelected || view.isActivated)
                assertEquals(1f, view.alpha, 0f)
            }
            recordSageScreen("05-v52-row-after")

            onView(withId(R.id.inventory_add_item)).perform(click())
            onView(withId(R.id.inventory_item_name)).perform(replaceText("Fictional oats"), closeSoftKeyboard())
            onView(withId(R.id.inventory_item_quantity)).perform(replaceText("3"), closeSoftKeyboard())
            onView(withId(android.R.id.button1)).perform(click())
            onView(withId(R.id.inventory_success_dismiss)).perform(click())
            val direct = onView(withText("Added directly"))
            direct.perform(sageScrollTo(), click())
            onView(withText("Fictional oats")).check(matches(isDisplayed()))
            direct.perform(click())
            onView(withText("Fictional oats")).check(matches(not(isDisplayed())))
            onView(withId(R.id.inventory_search)).perform(replaceText("rice"), closeSoftKeyboard())
            selectInventorySort("Product name A–Z")
            selectInventoryFilter("Demo")
            onView(withText("Jasmine Rice 5kg")).check(matches(isDisplayed()))
        }
    }

    private fun heldInventoryTouch(interaction: androidx.test.espresso.ViewInteraction, name: String) {
        lateinit var tap: View
        val bounds = android.graphics.Rect()
        interaction.check { view, missing ->
            if (missing != null) throw missing
            tap = generateSequence(view) { it.parent as? View }.first { it.isClickable }
            assertTrue(tap.getGlobalVisibleRect(bounds))
        }
        val automation = instrumentation.uiAutomation
        val before = checkNotNull(automation.takeScreenshot())
        val downTime = SystemClock.uptimeMillis()
        fun send(action: Int) {
            val e = android.view.MotionEvent.obtain(downTime, SystemClock.uptimeMillis(), action,
                bounds.exactCenterX(), bounds.exactCenterY(), 0)
            e.source = android.view.InputDevice.SOURCE_TOUCHSCREEN
            try { assertTrue(automation.injectInputEvent(e, true)) } finally { e.recycle() }
        }
        try {
            send(android.view.MotionEvent.ACTION_DOWN)
            SystemClock.sleep(150)
            instrumentation.runOnMainSync { assertTrue(tap.isPressed); assertEquals(1f, tap.alpha, 0f) }
            val pressed = checkNotNull(automation.takeScreenshot())
            val colors = listOf(Color.parseColor("#304C38"), Color.parseColor("#697665"), Color.parseColor("#426348"))
            val unchanged = IntArray(colors.size)
            val tint = Color.parseColor("#EDF2E9")
            var backgroundPixels = 0
            for (y in bounds.top until bounds.bottom) for (x in bounds.left until bounds.right) {
                val initial = before.getPixel(x, y)
                val current = pressed.getPixel(x, y)
                val index = colors.indexOf(initial)
                if (index >= 0 && initial == current) unchanged[index]++
                if (initial == Color.WHITE && current == tint) backgroundPixels++
            }
            assertTrue("Native paint includes the light pressed background", backgroundPixels > 100)
            assertTrue("Native glyphs and icons retain their solid colors", unchanged.all { it > 10 })
            pressed.recycle()
            if (InstrumentationRegistry.getArguments().getString("sageScreenshots") == "true") {
                android.os.ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(
                    "screencap -p /data/local/tmp/sage-v5-native/" + name + ".png",
                )).use { it.readBytes() }
            }
        } finally {
            send(android.view.MotionEvent.ACTION_UP)
            before.recycle()
        }
    }

    private fun edit(id: Int, value: String) {
        onView(withId(id)).perform(sageScrollTo(), replaceText(value), closeSoftKeyboard())
    }

    private fun withManualForm(action: (ActivityScenario<MainActivity>) -> Unit) {
        val image = File.createTempFile("sage-v51-", ".png", context.cacheDir)
        val bitmap = Bitmap.createBitmap(90, 130, Bitmap.Config.ARGB_8888)
        bitmap.eraseColor(Color.WHITE)
        image.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
        Intents.init()
        try {
            val picker = if (Build.VERSION.SDK_INT >= 33) MediaStore.ACTION_PICK_IMAGES else Intent.ACTION_OPEN_DOCUMENT
            Intents.intending(hasAction(picker)).respondWith(ActivityResult(Activity.RESULT_OK, Intent().setData(Uri.fromFile(image))))
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                if (compact) {
                    scenario.onActivity { enlargeSageTestText(it); refreshInventoryFixture(it) }
                    recordSageScreen("14b-v51-large-brand")
                }
                onView(withId(R.id.home_add_receipt)).perform(click())
                onView(withId(R.id.add_import_image)).perform(sageScrollTo(), click())
                onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
                onView(withText(R.string.preview_cancel)).check(doesNotExist())
                recordSageScreen("02-v51-preview")
                onView(withId(R.id.preview_continue)).perform(sageScrollTo(), click())
                recordSageScreen("03-v51-manual")
                action(scenario)
            }
        } finally {
            Intents.release()
            image.delete()
        }
    }
}
