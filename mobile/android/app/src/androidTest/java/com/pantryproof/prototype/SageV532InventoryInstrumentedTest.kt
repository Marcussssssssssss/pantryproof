package com.pantryproof.prototype

import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.closeSoftKeyboard
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.RootMatchers.isPlatformPopup
import androidx.test.espresso.matcher.ViewMatchers.isCompletelyDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withTagValue
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryMetadata
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.ManualInventoryStore
import org.hamcrest.Matchers.containsString
import org.hamcrest.Matchers.equalTo
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDate

@RunWith(AndroidJUnit4::class)
class SageV532InventoryInstrumentedTest {
    private val instrument = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrument.targetContext
    private val store get() = ManualInventoryStore(context)
    private val fruit = InventoryCategory.VEGETABLES_FRUITS
    private val dry = InventoryCategory.DRY_FOOD
    private val addedNames = mutableSetOf<String>()

    @After fun removeFixtures() {
        assertNotNull(store.update { items ->
            items.filterNot { it.id.startsWith("manual-inventory-v532-") || it.name in addedNames }
        })
    }

    @Test fun categoryCardsSurviveInterleavedWritesAndBrowseChanges() {
        val pear = stock("pear", "Fixture pears", "10", fruit)
        val barley = stock("barley", "Fixture barley", "3", dry)
        val apple = stock("apple", "Fixture apples", "0.750", fruit)
        val before = listOf(pear, barley, apple)
        assertNotNull(store.update { it + before })
        lateinit var existing: InventoryItem
        lateinit var extra: InventoryItem
        ActivityScenario.launch(MainActivity::class.java).use { scene ->
            awaitHouseholdInventory(scene)
            scene.onActivity {
                assertEquals(listOf("Other / Uncategorized", "Vegetables & Fruits", "Dry Food"), categories(it))
                assertCategory(it, "Vegetables & Fruits", "2 items", pear.id, apple.id)
                assertGroupState(it, "Dry Food", false)
            }
            tapCategory("Vegetables & Fruits")
            screenshot("01-before-addition")
            existing = add("Fixture apricots", "2", "Vegetables & Fruits")
            assertBanner(scene, R.string.v51_item_added)
            scene.onActivity {
                assertCategory(it, "Vegetables & Fruits", "3 items", pear.id, apple.id, existing.id)
                assertGroupState(it, "Vegetables & Fruits", true)
                assertGroupState(it, "Dry Food", false)
            }
            screenshot("02-added-to-existing-category")
            val gap = dismissAndCheckRestoredLayout(scene)
            assertTrue(gap > 0)
            screenshot("03-notification-dismissed")
            extra = add("Fixture milk", "1", "Dairy & Eggs")
            assertBanner(scene, R.string.v51_item_added)
            onView(withText(containsString(context.getString(R.string.v51_stock_hidden)))).check(matches(isDisplayed()))
            scene.onActivity {
                assertCategory(it, "Dairy & Eggs", "1 item", extra.id)
                assertGroupState(it, "Dairy & Eggs", false)
            }
            dismissAndCheckRestoredLayout(scene)
            val uncategorized = add("Fixture uncategorized item", "1")
            dismissAndCheckRestoredLayout(scene)
            tapCategory("Other / Uncategorized")
            onView(withText(uncategorized.name)).perform(sageScrollTo()).check(matches(isDisplayed()))
            screenshot("04-added-uncategorized")

            openSageInventoryDetails(existing.id)
            onView(withTagValue(equalTo("inventory-edit:" + existing.id))).perform(sageScrollTo(), click())
            chooseCategory("Dry Food")
            onView(withId(android.R.id.button1)).perform(click())
            assertBanner(scene, R.string.v51_changes_saved)
            dismissAndCheckRestoredLayout(scene)
            scene.onActivity {
                assertCategory(it, "Vegetables & Fruits", "2 items", pear.id, apple.id)
                assertCategory(it, "Dry Food", "2 items", barley.id, existing.id)
                assertGroupState(it, "Dry Food", false)
            }
            tapCategory("Dry Food")
            screenshot("05-after-category-edit")
            openSageInventoryDetails(existing.id)
            onView(withTagValue(equalTo("inventory-increase:" + existing.id))).perform(click())
            pressBack()
            assertBanner(scene, R.string.v51_quantity_updated)
            dismissAndCheckRestoredLayout(scene)
            assertEquals(existing.copy(quantity = "3".toBigDecimal(), household = InventoryMetadata(dry)),
                store.load()!!.single { it.id == existing.id })
            openSageInventoryDetails(uncategorized.id)
            onView(withTagValue(equalTo("inventory-delete:" + uncategorized.id))).perform(sageScrollTo(), click())
            onView(withId(android.R.id.button1)).perform(click())
            assertBanner(scene, R.string.v51_item_removed)
            dismissAndCheckRestoredLayout(scene)
            assertEquals(before + existing.copy(quantity = "3".toBigDecimal(), household = InventoryMetadata(dry)) + extra,
                store.load()!!)

            for ((sort, order) in listOf(
                "Product name A–Z" to listOf(apple.id, pear.id),
                "Quantity low to high" to listOf(apple.id, pear.id),
                "Quantity high to low" to listOf(pear.id, apple.id),
                "Original order" to listOf(pear.id, apple.id),
            )) {
                selectInventorySort(sort)
                scene.onActivity { assertCategory(it, "Vegetables & Fruits", "2 items", *order.toTypedArray()) }
            }
            tapCategory("Dry Food")
            selectInventoryFilter("Direct")
            scene.onActivity {
                assertEquals(listOf("Vegetables & Fruits", "Dry Food", "Dairy & Eggs"), categories(it))
                assertGroupState(it, "Dry Food", true)
            }
            onView(withId(R.id.inventory_search)).perform(replaceText("barley"), closeSoftKeyboard())
            scene.onActivity {
                assertEquals(listOf("Dry Food"), categories(it))
                assertCategory(it, "Dry Food", "1 item", barley.id)
                assertGroupState(it, "Dry Food", true)
            }
            tapCategory("Dry Food")
            scene.recreate()
            onView(withId(R.id.inventory_search)).check(matches(withText("barley")))
            scene.onActivity { assertGroupState(it, "Dry Food", false) }
            onView(withId(R.id.inventory_clear_search)).perform(click(), closeSoftKeyboard())
            selectInventoryFilter("All")
            scene.onActivity {
                assertGroupState(it, "Dry Food", false)
                assertGroupState(it, "Vegetables & Fruits", true)
            }
            onView(withId(R.id.receipt_history)).perform(click())
            onView(withId(R.id.app_bar_back)).perform(click())
            scene.onActivity {
                assertGroupState(it, "Dry Food", false)
                assertGroupState(it, "Vegetables & Fruits", true)
            }
            onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click(), click())
            scene.onActivity { categories(it).forEach { title -> assertGroupState(it, title, true) } }
            onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click())
            scene.onActivity { categories(it).forEach { title -> assertGroupState(it, title, false) } }
        }
        ActivityScenario.launch(MainActivity::class.java).use { scene ->
            awaitHouseholdInventory(scene)
            scene.onActivity {
                assertCategory(it, "Vegetables & Fruits", "2 items", pear.id, apple.id)
                assertCategory(it, "Dry Food", "2 items", barley.id, existing.id)
                assertCategory(it, "Dairy & Eggs", "1 item", extra.id)
                assertGroupState(it, "Vegetables & Fruits", false)
            }
        }
    }

    @Test fun adaptiveBannerReservesSpaceAndDismissesAutomatically() {
        ActivityScenario.launch(MainActivity::class.java).use { scene ->
            awaitHouseholdInventory(scene)
            applyNarrowText(scene)
            var summaryBefore = 0
            scene.onActivity { summaryBefore = bounds(it.findViewById(R.id.inventory_summary)).top }
            add("Fixture narrow item", "2", "Dry Food")
            assertBanner(scene, R.string.v51_item_added)
            screenshot("06-adaptive-notification")
            val deadline = SystemClock.uptimeMillis() + 8_000
            var hidden = false
            while (!hidden && SystemClock.uptimeMillis() < deadline) {
                scene.onActivity { hidden = it.findViewById<View>(R.id.inventory_success_host).visibility == View.GONE }
                if (!hidden) SystemClock.sleep(100)
            }
            assertTrue("Banner timed out", hidden)
            scene.onActivity {
                assertEquals(summaryBefore, bounds(it.findViewById(R.id.inventory_summary)).top)
            }
            screenshot("07-adaptive-after-timeout")
        }
    }

    @Test fun floatingScanLeavesFinalRowClearInPortraitAndLandscape() {
        withLargeInventory { scene ->
            assertFinalRowClear(scene, "08-scroll-clearance-portrait")
            scene.onActivity { it.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE }
            val deadline = SystemClock.uptimeMillis() + 6_000
            var landscape = false
            while (!landscape && SystemClock.uptimeMillis() < deadline) {
                scene.onActivity { landscape = it.resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE }
                if (!landscape) SystemClock.sleep(50)
            }
            assertTrue(landscape)
            awaitHouseholdInventory(scene)
            assertFinalRowClear(scene, "09-scroll-clearance-landscape")
        }
    }

    @Test fun floatingScanLeavesFinalRowClearWithNarrowLargeText() {
        withLargeInventory { scene ->
            applyNarrowText(scene)
            assertFinalRowClear(scene, "10-scroll-clearance-narrow")
        }
    }

    private fun withLargeInventory(action: (ActivityScenario<MainActivity>) -> Unit) {
        val rows = List(18) { stock("long-$it", "Fixture product $it", "1", dry) } + finalItem()
        assertNotNull(store.update { it + rows })
        ActivityScenario.launch(MainActivity::class.java).use { scene ->
            awaitHouseholdInventory(scene)
            action(scene)
        }
    }

    private fun finalItem() = stock("last", "Fixture final oats", "0.750", dry).let {
        it.copy(household = InventoryMetadata(dry, LocalDate.now().plusDays(1), "1.000".toBigDecimal()))
    }

    private fun assertFinalRowClear(scene: ActivityScenario<MainActivity>, shot: String) {
        var scanBefore = Rect()
        var open = false
        scene.onActivity {
            scanBefore = bounds(it.findViewById(R.id.home_add_receipt))
            open = ViewCompat.getStateDescription(header(it, "Dry Food")) == it.getString(R.string.sage_expanded)
        }
        if (!open) onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click())
        lateinit var scroll: ScrollView
        scene.onActivity { activity ->
            val last = activity.findViewById<ViewGroup>(R.id.inventory_browse_results).findViewWithTag<View>(finalItem().id)
            scroll = generateSequence(last.parent) { it.parent }.filterIsInstance<ScrollView>().first()
            scroll.scrollTo(0, scroll.getChildAt(0).height)
            val scan = activity.findViewById<View>(R.id.home_add_receipt)
            assertEquals(scanBefore, bounds(scan))
            assertTrue(scroll.clipToPadding)
            assertTrue(scroll.scrollY > 0)
            assertTrue("The complete last row clears the scan button", bounds(last).bottom < bounds(scan).top)
            assertTrue("The top of the last row remains visible", bounds(last).top >= bounds(scroll).top)
            assertEquals(listOf(finalItem().name, "Exp: Tomorrow", "0.750 kg", "Expiring soon", "Low stock"),
                allViews(last).filterIsInstance<TextView>().map { it.text.toString() }.toList())
            val root = activity.findViewById<ViewGroup>(R.id.screen_inventory)
            val inset = ViewCompat.getRootWindowInsets(root)!!.getInsets(WindowInsetsCompat.Type.navigationBars()).bottom
            assertEquals(inset, root.paddingBottom)
            val parent = scan.parent as View
            assertEquals((scan.layoutParams as ViewGroup.MarginLayoutParams).bottomMargin, parent.height - scan.bottom)
        }
        screenshot(shot)
        onView(withTagValue(equalTo(finalItem().id))).check(matches(isCompletelyDisplayed())).perform(click())
        onView(withId(R.id.sage_inventory_details)).check(matches(isDisplayed()))
        onView(withText("0.750 kg")).check(matches(isDisplayed()))
        scene.onActivity {
            assertEquals(View.INVISIBLE, it.findViewById<View>(R.id.home_add_receipt).visibility)
            assertEquals(0, scroll.paddingBottom)
        }
        if (shot.contains("portrait")) screenshot("11-final-item-management")
        pressBack()
        scene.onActivity { assertEquals(scanBefore, bounds(it.findViewById(R.id.home_add_receipt))) }
    }

    private fun applyNarrowText(scene: ActivityScenario<MainActivity>) {
        scene.onActivity { activity ->
            val resources = activity.resources
            val config = Configuration(resources.configuration).apply { fontScale = 1.5f }
            @Suppress("DEPRECATION")
            resources.updateConfiguration(config, resources.displayMetrics)
            assertEquals(1.5f, resources.configuration.fontScale, 0f)
            assertTrue(resources.configuration.screenWidthDp <= 320)
            refreshInventoryFixture(activity)
        }
    }

    private fun add(name: String, quantity: String, category: String? = null): InventoryItem {
        addedNames += name
        onView(withId(R.id.inventory_add_item)).perform(click())
        onView(withId(R.id.inventory_item_name)).perform(sageScrollTo(), replaceText(name), closeSoftKeyboard())
        onView(withId(R.id.inventory_item_quantity)).perform(sageScrollTo(), replaceText(quantity), closeSoftKeyboard())
        category?.let(::chooseCategory)
        onView(withId(android.R.id.button1)).perform(click())
        return store.load()!!.single { it.name == name }
    }

    private fun chooseCategory(label: String) {
        onView(withId(R.id.inventory_category)).perform(sageScrollTo(), click())
        onData(equalTo(label)).inRoot(isPlatformPopup()).inAdapterView(withId(R.id.inventory_category_choices)).perform(click())
    }

    private fun assertBanner(scene: ActivityScenario<MainActivity>, title: Int) {
        onView(withText(title)).check(matches(isDisplayed()))
        scene.onActivity(::assertInventorySuccessPlacement)
    }

    private fun dismissAndCheckRestoredLayout(scene: ActivityScenario<MainActivity>): Int {
        var before = 0
        var slotHeight = 0
        scene.onActivity {
            before = bounds(it.findViewById(R.id.inventory_summary)).top
            slotHeight = bounds(it.findViewById(R.id.inventory_success_host)).height()
        }
        onView(withId(R.id.inventory_success_dismiss)).perform(click())
        var released = 0
        scene.onActivity {
            assertEquals(View.GONE, it.findViewById<View>(R.id.inventory_success_host).visibility)
            released = before - bounds(it.findViewById(R.id.inventory_summary)).top
            assertEquals("Dismissal restores the full notification slot", slotHeight, released)
        }
        return released
    }

    private fun tapCategory(label: String) = onView(withText(label)).perform(sageScrollTo(), click())

    private fun titles(activity: MainActivity) = allViews(activity.findViewById(R.id.sage_inventory_groups))
        .filterIsInstance<TextView>().filter { it.id == R.id.sage_action_title }

    private fun categories(activity: MainActivity) = titles(activity).map { it.text.toString() }.toList()

    private fun header(activity: MainActivity, label: String) =
        titles(activity).single { it.text.toString() == label }.parent.parent as View

    private fun assertCategory(activity: MainActivity, label: String, count: String, vararg ids: String) {
        val head = header(activity, label)
        assertEquals(count, head.findViewById<TextView>(R.id.sage_action_subtitle).text.toString())
        val cardRows = allViews(head.parent as View).filter { it.tag is String }.map { it.tag as String }.toList()
        assertEquals(ids.toList(), cardRows)
        ids.forEach { id ->
            assertEquals(1, allViews(activity.findViewById(R.id.inventory_browse_results)).count { it.tag == id })
        }
    }

    private fun assertGroupState(activity: MainActivity, label: String, open: Boolean) {
        val header = header(activity, label)
        assertEquals(activity.getString(if (open) R.string.sage_expanded else R.string.sage_collapsed),
            ViewCompat.getStateDescription(header))
        assertFalse(header.isPressed || header.isSelected || header.isActivated)
    }

    private fun stock(id: String, name: String, quantity: String, category: InventoryCategory) =
        InventoryItem("manual-inventory-v532-$id", name, quantity.toBigDecimal(), ManualInventoryStore.STANDALONE_ROW_STATE,
            InventoryUnit.KILOGRAM, InventoryMetadata(category))

    private fun screenshot(name: String) {
        if (InstrumentationRegistry.getArguments().getString("sage532Screenshots") != "true") return
        instrument.waitForIdleSync()
        SystemClock.sleep(350)
        val bitmap = checkNotNull(instrument.uiAutomation.takeScreenshot())
        try {
            File(context.filesDir, "sage532-$name.png").outputStream().use {
                assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it))
            }
        } finally {
            bitmap.recycle()
        }
    }
}

internal fun assertInventorySuccessPlacement(activity: MainActivity) {
    val banner = bounds(activity.findViewById(R.id.inventory_success))
    val root = activity.findViewById<View>(R.id.screen_inventory)
    val appName = allViews(root).filterIsInstance<TextView>().single { it.text == activity.getText(R.string.app_name) }
    assertTrue("App name is above the banner", bounds(appName).bottom <= banner.top)
    for (id in listOf(R.id.pantry_brand_logo, R.id.sage_development_tools, R.id.receipt_history, R.id.inventory_add_item)) {
        assertTrue("Header element is above the banner", bounds(activity.findViewById(id)).bottom <= banner.top)
    }
    val summary = bounds(activity.findViewById(R.id.inventory_summary))
    assertTrue("Count follows the banner", summary.top >= banner.bottom)
    for (id in listOf(R.id.inventory_search, R.id.inventory_sort, R.id.inventory_filter)) {
        assertTrue("Control follows the count", bounds(activity.findViewById(id)).top >= summary.bottom)
    }
}

private fun allViews(view: View): Sequence<View> = sequence {
    yield(view)
    if (view is ViewGroup) repeat(view.childCount) { yieldAll(allViews(view.getChildAt(it))) }
}

private fun bounds(view: View): Rect {
    val xy = IntArray(2).also(view::getLocationOnScreen)
    assertTrue("Visible bounds for " + view.id, view.isShown && view.width > 0 && view.height > 0)
    return Rect(xy[0], xy[1], xy[0] + view.width, xy[1] + view.height)
}

