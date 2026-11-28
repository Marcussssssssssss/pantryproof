package com.pantryproof.prototype

import android.os.ParcelFileDescriptor.AutoCloseInputStream
import android.os.SystemClock
import android.content.res.Configuration
import android.graphics.Rect
import android.view.View
import android.widget.ScrollView
import android.graphics.drawable.ColorDrawable
import android.util.TypedValue
import android.widget.CheckedTextView
import android.widget.EditText
import android.widget.ListView
import androidx.core.view.ViewCompat
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.closeSoftKeyboard
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isCompletelyDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isSelected
import androidx.test.espresso.matcher.ViewMatchers.withContentDescription
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.ui.PantryUiState
import org.hamcrest.Matchers.not
import org.hamcrest.Matchers.equalTo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SagePresentationInstrumentedTest {
    @Test fun inventoryLaunchSheetsAndDevelopmentPreserveTheRoot() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            val compact = InstrumentationRegistry.getArguments().getString("v4Compact") == "true"
            if (compact) scenario.onActivity { enlargeSageTestText(it); refreshInventoryFixture(it) }
            onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
            onView(withId(R.id.screen_home)).check(doesNotExist())
            onView(withId(R.id.sage_nav_inventory)).check(doesNotExist())
            onView(withId(R.id.app_bar_back)).check(doesNotExist())
            onView(withId(R.id.inventory_add_item)).check(matches(withContentDescription(R.string.v5_inventory_add_description)))
            if (compact) onView(withText(R.string.app_name)).check { view, missing ->
                if (missing != null) throw missing
                assertEquals(1, (view as android.widget.TextView).lineCount)
            }
            onView(withId(R.id.home_add_receipt)).check(matches(isCompletelyDisplayed()))
            recordSageScreen(if (compact) "01-v5-inventory-compact-200" else "01-v5-inventory-launch")
            onView(withText("Jasmine Rice 5kg")).check(matches(not(isDisplayed())))
            recordSageScreen("03-v5-groups-collapsed")
            onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click())
            onView(withText("Jasmine Rice 5kg")).perform(sageScrollTo()).check(matches(isDisplayed()))
            recordSageScreen("04-v5-groups-expanded")
            openSageInventoryDetails("stock-rice")
            onView(withId(R.id.inventory_stock_rice_value)).check(matches(withText("1")))
            recordSageScreen("09-v5-item-management")
            pressBack()
            onView(withId(R.id.inventory_add_item)).perform(click())
            onView(withId(R.id.inventory_item_quantity)).check(matches(withText("")))
            recordSageScreen("08-v5-add-item-sheet")
            onView(withId(R.id.inventory_item_name)).perform(replaceText("Discarded draft"))
            onView(withId(R.id.inventory_item_quantity)).perform(replaceText("5"), closeSoftKeyboard())
            onView(withContentDescription(R.string.sage_close)).perform(click())
            onView(withText("Discarded draft")).check(doesNotExist())
            onView(withId(R.id.home_add_receipt)).perform(click())
            onView(withId(R.id.screen_add_receipt)).check(matches(isDisplayed()))
            recordSageScreen(if (compact) "11-v5-source-sheet-compact-200" else "11-v5-source-sheet")
            pressBack()
            onView(withId(R.id.home_add_receipt)).check(matches(isCompletelyDisplayed()))
            onView(withId(R.id.sage_development_tools)).perform(click())
            onView(withId(R.id.screen_development)).check(matches(isDisplayed()))
            onView(withId(R.id.home_add_receipt)).check(doesNotExist())
            recordSageScreen("16-v5-development")
            pressBack()
            onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
            androidx.test.espresso.Espresso.pressBackUnconditionally()
            val deadline = SystemClock.uptimeMillis() + 5_000
            while (scenario.state != androidx.lifecycle.Lifecycle.State.DESTROYED &&
                SystemClock.uptimeMillis() < deadline
            ) {
                SystemClock.sleep(50)
            }
            assertEquals(androidx.lifecycle.Lifecycle.State.DESTROYED, scenario.state)
        }
    }

    @Test fun previewReturnsDirectlyToInventoryAndItsExistingBrowseState() {
        ActivityScenario.launch(MainActivity::class.java).use {
            onView(withId(R.id.inventory_search)).perform(replaceText("rice"), closeSoftKeyboard())
            selectInventorySort("Product name A–Z")
            selectInventoryFilter("Demo")
            openSyntheticPreviewFromAddReceipt()
            onView(withId(R.id.home_add_receipt)).check(doesNotExist())
            onView(withId(R.id.screen_add_receipt)).check(doesNotExist())
            onView(withText("Step 1 of 3")).check(matches(isDisplayed()))
            recordSageScreen("12b-v5-numbered-preview")
            onView(withId(R.id.app_bar_back)).perform(click())
            onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
            onView(withId(R.id.inventory_search)).check(matches(withText("rice")))
            onView(withId(R.id.inventory_filter)).check(matches(isSelected()))
            onView(withId(R.id.screen_add_receipt)).check(doesNotExist())
        }
    }

    @Test fun pinnedControlsAndScanStayReachableWhileTheLastRowClearsTheButton() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            val compact = InstrumentationRegistry.getArguments().getString("v4Compact") == "true"
            scenario.onActivity { activity ->
                if (compact) enlargeSageTestText(activity)
                val field = MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }
                val inventory = (field.get(activity) as PantryUiState).inventory
                repeat(15) { index ->
                    inventory.add(InventoryItem("stock-v5-" + index, "Fixture item " + (index + 1), 1, "In pantry"))
                }
                refreshInventoryFixture(activity)
            }
            selectInventorySort("Quantity high to low")
            fun bounds(view: View) = Rect().also { assertTrue(view.getGlobalVisibleRect(it)) }
            lateinit var header: Rect
            lateinit var scan: Rect
            scenario.onActivity { activity ->
                header = bounds(activity.findViewById(R.id.inventory_pinned_controls))
                scan = bounds(activity.findViewById(R.id.home_add_receipt))
                val rows = activity.findViewById<View>(R.id.inventory_browse_results)
                val scroll = generateSequence(rows.parent) { it.parent }.filterIsInstance<ScrollView>().first()
                scroll.fullScroll(View.FOCUS_DOWN)
            }
            onView(withText("Fixture item 15")).check(matches(isCompletelyDisplayed()))
            scenario.onActivity { activity ->
                assertEquals(header, bounds(activity.findViewById(R.id.inventory_pinned_controls)))
                assertEquals(scan, bounds(activity.findViewById(R.id.home_add_receipt)))
                val last = activity.findViewById<View>(R.id.inventory_browse_results)
                    .findViewWithTag<View>("stock-v5-14")
                assertTrue(bounds(last).bottom <= scan.top)
            }
            recordSageScreen(if (compact) "05-v5-scrolled-compact-200" else "05-v5-inventory-scrolling")
        }
    }

    @Test fun inventoryLaunchReportsInvalidStorageAndLeavesItsBytesIntact() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val snapshot = context.filesDir.resolve("manual-inventory.json")
        val previous = snapshot.takeIf { it.isFile }?.readBytes()
        val invalid = """{"version":999,"rows":[]}""".toByteArray()
        try {
            snapshot.writeBytes(invalid)
            ActivityScenario.launch(MainActivity::class.java).use {
                onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
                onView(withText(R.string.manual_inventory_load_failed_title)).check(matches(isDisplayed()))
                org.junit.Assert.assertArrayEquals(invalid, snapshot.readBytes())
            }
        } finally {
            if (previous == null) snapshot.delete() else snapshot.writeBytes(previous)
        }
    }

    @Test fun inventoryPopupKeepsTheSelectedOptionAndDismissalDoesNotSort() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            val compact = InstrumentationRegistry.getArguments().getString("v4Compact") == "true"
            if (compact) scenario.onActivity { enlargeSageTestText(it); refreshInventoryFixture(it) }
            onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
            onView(withText(R.string.inventory_sort_label)).check(doesNotExist())
            onView(withText(R.string.inventory_search_label)).check(doesNotExist())
            onView(withId(R.id.inventory_search)).check { view, missing ->
                if (missing != null) throw missing
                assertEquals("Search inventory...", view.createAccessibilityNodeInfo().hintText.toString())
            }
            onView(withId(R.id.inventory_add_item)).check(matches(isDisplayed()))
            recordSageScreen(if (compact) "02-v5-header-compact-200" else "02-v5-compact-header")
            fun openSort(selected: String) {
                onView(withId(R.id.inventory_sort)).perform(sageScrollTo(), click())
                onView(withId(R.id.inventory_sort_choices)).check { view, missing ->
                    if (missing != null) throw missing
                    val adapter = (view as ListView).adapter
                    assertEquals(listOf("Original order", "Product name A–Z", "Quantity low to high",
                        "Quantity high to low"), (0 until adapter.count).map { adapter.getItem(it).toString() })
                }
                onData(equalTo(selected)).inAdapterView(withId(R.id.inventory_sort_choices)).check { view, missing ->
                    if (missing != null) throw missing
                    val row = view as CheckedTextView
                    assertTrue(row.isChecked && row.createAccessibilityNodeInfo().isChecked)
                    assertEquals(row.context.getColor(R.color.pantry_primary_container),
                        (row.background as ColorDrawable).color)
                    assertEquals(row.context.getColor(R.color.pantry_primary), row.currentTextColor)
                    assertTrue(row.height >= 48 * row.resources.displayMetrics.density)
                    if (compact) {
                        assertTrue(row.resources.configuration.screenWidthDp <= 320)
                        assertEquals(2f, row.resources.configuration.fontScale, .01f)
                    }
                }
            }
            openSort("Original order")
            recordSageScreen(if (compact) "06-v5-sort-compact-200" else "06-v5-sort-popup")
            pressBack()
            scenario.onActivity {
                val sort = it.findViewById<android.view.View>(R.id.inventory_sort)
                assertEquals("Original order", ViewCompat.getStateDescription(sort).toString())
            }
            selectInventorySort("Quantity high to low")
            if (!compact) scenario.recreate()
            openSort("Quantity high to low")
            recordSageScreen(if (compact) "06b-v5-sort-selected-compact-200" else "06b-v5-sort-selected")
            pressBack()
            val filter = onView(withId(R.id.inventory_filter))
            filter.perform(click())
            onView(withId(R.id.inventory_filter_choices)).check { view, missing ->
                if (missing != null) throw missing
                val adapter = (view as ListView).adapter
                assertEquals(listOf("All", "Demo", "Receipt preview", "Manual", "Scanned", "Direct"),
                    (0 until adapter.count).map { adapter.getItem(it).toString() })
            }
            recordSageScreen(if (compact) "07-v5-filter-compact-200" else "07-v5-filter-popup")
            pressBack()
            filter.check(matches(not(isSelected())))
            selectInventoryFilter("Demo")
            filter.check(matches(isSelected()))
            filter.perform(click())
            onData(equalTo("Demo")).inAdapterView(withId(R.id.inventory_filter_choices)).check { row, missing ->
                if (missing != null) throw missing
                assertTrue((row as CheckedTextView).isChecked)
            }
            pressBack()
            scenario.onActivity {
                assertEquals("Demo", ViewCompat.getStateDescription(it.findViewById(R.id.inventory_filter)).toString())
                val tint = TypedValue()
                assertTrue(it.theme.resolveAttribute(android.R.attr.colorControlHighlight, tint, true))
                assertEquals(it.getColor(R.color.pantry_control_highlight), tint.data)
                assertTrue(it.theme.resolveAttribute(android.R.attr.textColorHighlight, tint, true))
                assertEquals(it.getColor(R.color.pantry_primary_container), tint.data)
            }
        }
    }

    @Test fun collapsedReviewRetainsDraftAndReopensTheFirstInvalidSection() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            openSyntheticPreviewFromAddReceipt()
            recordSageScreen("08-synthetic-preview")
            onView(withId(R.id.preview_continue)).perform(click())
            recordSageScreen("14-v5-receipt-details")
            onView(withId(R.id.details_review)).perform(click())
            recordSageScreen("15-v5-receipt-review")
            onView(withId(R.id.review_store_name)).perform(sageScrollTo(), replaceText("Sage fixture store"), closeSoftKeyboard())
            onView(withId(R.id.review_item_0_quantity)).perform(sageScrollTo(), replaceText(""), closeSoftKeyboard())
            onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click())
            onView(withId(R.id.review_store_name)).check(matches(not(isDisplayed())))
            onView(withId(R.id.review_confirm)).perform(click())
            scenario.onActivity { activity ->
                val quantity = activity.findViewById<EditText>(R.id.review_item_0_quantity)
                assertSame(quantity, activity.currentFocus)
                assertEquals("", quantity.text.toString())
            }
            recordSageScreen("14-review-validation")
            onView(withId(R.id.review_item_0_quantity)).perform(sageScrollTo(), replaceText("2"), closeSoftKeyboard())
            onView(withText(R.string.details_summary_title)).perform(sageScrollTo(), click())
            onView(withId(R.id.review_store_name)).check(matches(withText("Sage fixture store")))
            onView(withId(R.id.review_confirm)).perform(click())
            onView(withId(R.id.sage_result_sheet)).check(matches(isDisplayed()))
            recordSageScreen("17-temporary-result")
            onView(withId(R.id.review_view_inventory)).perform(sageScrollTo(), click())
            onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
        }
    }
}

/** Apply the accessibility size to the test activity's resources only. */
@Suppress("DEPRECATION")
internal fun enlargeSageTestText(activity: MainActivity) {
    val resources = activity.resources
    resources.updateConfiguration(Configuration(resources.configuration).apply {
        fontScale = 2f
    }, resources.displayMetrics)
}

/** Screenshots are opt-in and written only to the disposable device's shell directory. */
internal fun recordSageScreen(name: String) {
    if (InstrumentationRegistry.getArguments().getString("sageScreenshots") != "true") return
    require(name.matches(Regex("[a-z0-9-]+")))
    // Let platform ripples and slider thumb animations settle before recording evidence.
    SystemClock.sleep(350)
    val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
    AutoCloseInputStream(automation.executeShellCommand("mkdir -p /data/local/tmp/sage-v5-native")).use { it.readBytes() }
    AutoCloseInputStream(automation.executeShellCommand(
        "screencap -p /data/local/tmp/sage-v5-native/" + name + ".png",
    )).use { it.readBytes() }
}
