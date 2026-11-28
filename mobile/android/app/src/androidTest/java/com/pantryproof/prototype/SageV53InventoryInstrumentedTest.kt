package com.pantryproof.prototype

import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.SystemClock
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryMetadata
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.PurchaseDateInput
import org.hamcrest.Matchers.not
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDate

@RunWith(AndroidJUnit4::class)
class SageV53InventoryInstrumentedTest {
    private val instrument = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrument.targetContext
    private val fruit = InventoryCategory.VEGETABLES_FRUITS
    private val dry = InventoryCategory.DRY_FOOD
    private val longName = "Long-grain fragrant brown rice with roasted garlic and dried vegetables"

    @Test fun compactRowsKeepExactQuantitiesDatesWarningsAndSources() {
        val today = LocalDate.now()
        val normal = item("normal", "Garden tomatoes", "2", fruit, unit = InventoryUnit.UNKNOWN)
        val later = item("later", "Green apples", "0.750", fruit, today.plusDays(8))
        val current = item("today", "Baby spinach", "0.250", fruit, today)
        val tomorrow = item("tomorrow", "Fresh strawberries", "0.750", fruit, today.plusDays(1), "1.000")
        val soon = item("soon", "Organic celery", "0.000", fruit, today.plusDays(2))
        val expired = item("expired", "Salad leaves", "0.750", fruit, today.minusDays(1), "0.750")
        val long = item("long", longName, "123456.750", dry)
        val rice = item("rice", "Rice, explicitly assigned fixture", "1.000", InventoryCategory.HOUSEHOLD_SUPPLIES)
        val milk = item("milk", "Milk", "2", InventoryCategory.DAIRY_EGGS, unit = InventoryUnit.LITRE)
        val fish = item("fish", "Fish", "500", InventoryCategory.MEAT_SEAFOOD, unit = InventoryUnit.GRAM)
        val store = ManualInventoryStore(context)
        val items = listOf(normal, later, current, tomorrow, soon, expired, long, rice, milk, fish)
        val ids = items.mapTo(hashSetOf()) { it.id }
        assertNotNull(store.update { it + items })
        try {
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                awaitHouseholdInventory(scenario)
                val category = onView(withText("Vegetables & Fruits"))
                onView(withText(normal.name)).check(matches(not(isDisplayed())))
                scenario.onActivity { assertCategoryHeaders(it) }
                screenshot("01-compact-home")
                category.perform(sageScrollTo(), click())
                onView(withText(normal.name)).check(matches(isDisplayed()))
                scenario.onActivity { activity ->
                    assertCategoryHeaders(activity, expanded = "Vegetables & Fruits")
                    val name = text(row(activity, normal), normal.name)
                    assertTextSize(name, 16f)
                    assertEquals(listOf(normal.name, "2"), texts(row(activity, normal)).map { it.text.toString() })
                    assertEquals(listOf(later.name, "Exp: ${PurchaseDateInput.display(today.plusDays(8))}", "0.750 kg"),
                        texts(row(activity, later)).map { it.text.toString() })
                    assertEquals("Exp: Today", text(row(activity, current), "Exp: Today").text.toString())
                    assertEquals("Exp: Tomorrow", text(row(activity, tomorrow), "Exp: Tomorrow").text.toString())
                    val past = row(activity, expired)
                    text(past, "Exp: ${PurchaseDateInput.display(today.minusDays(1))}")
                    val expiredLabel = text(past, "Expired")
                    val lowStockLabel = text(past, "Low stock")
                    assertLabel(expiredLabel, "#F9DDDD", "#A32C2C")
                    assertLabel(lowStockLabel, "#F6E2DA", "#944331")
                    assertEquals(position(expiredLabel)[1], position(lowStockLabel)[1])
                    assertTrue(position(expiredLabel)[0] + expiredLabel.width < position(lowStockLabel)[0])
                    assertLabel(text(row(activity, soon), "Out of stock"), "#F9DDDD", "#A32C2C")
                    assertLabel(text(row(activity, tomorrow), "Expiring soon"), "#FFF0D6", "#87580F")
                    assertLabel(text(row(activity, current), "Expires today"), "#FFF0D6", "#87580F")
                    val quantity = text(past, "0.750 kg")
                    assertEquals(position(text(row(activity, later), "0.750 kg"))[0], position(quantity)[0])
                    assertEquals(position(text(past, expired.name))[1], position(quantity)[1])
                    val node = past.createAccessibilityNodeInfo()
                    assertEquals("android.widget.Button", node.className)
                    assertTrue(node.contentDescription.contains("Expired. Low stock"))
                    assertTrue(node.actionList.contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_CLICK))
                    assertTrue(past.isFocusable)
                    assertTrue(past.height >= (48 * activity.resources.displayMetrics.density).toInt())
                }
                screenshot("02-expanded-category")
                onView(withText(expired.name)).perform(sageScrollTo()).check(matches(isDisplayed()))
                screenshot("03-expiry-and-warning-labels")
                openSageInventoryDetails(tomorrow.id)
                onView(withText("Source: Direct inventory addition")).check(matches(isDisplayed()))
                onView(withText("Expiry date: ${PurchaseDateInput.display(today.plusDays(1))}")).check(matches(isDisplayed()))
                screenshot("04-management-source-and-full-date")
                pressBack()
                scenario.onActivity { assertFalse(row(it, tomorrow).isPressed || row(it, tomorrow).isSelected) }

                onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click())
                onView(withText(normal.name)).check(matches(not(isDisplayed())))
                onView(withId(R.id.sage_expand_all)).perform(sageScrollTo(), click())
                onView(withText(rice.name)).perform(sageScrollTo()).check(matches(isDisplayed()))
                assertEquals(InventoryCategory.HOUSEHOLD_SUPPLIES, store.load()!!.single { it.id == rice.id }.household.category)
                onView(withText(long.name)).perform(sageScrollTo()).check(matches(isDisplayed()))
                scenario.onActivity {
                    val longRow = row(it, long)
                    assertTrue(text(longRow, longName).lineCount > 1)
                    assertEquals(0, text(longRow, longName).layout.getEllipsisCount(0))
                    assertEquals("123456.750 kg", text(longRow, "123456.750 kg").text.toString())
                    assertEquals("Fictional demo", text(it.findViewById<ViewGroup>(R.id.inventory_browse_results)
                        .findViewWithTag("stock-rice"), "Fictional demo").text.toString())
                }
                screenshot("05-long-name-and-fractional-quantity")
            }
        } finally {
            assertNotNull(store.update { rows -> rows.filterNot { it.id in ids } })
        }
    }

    @Test fun narrowLargeTextWrapsBothWarningsWithoutClipping() {
        val today = LocalDate.now()
        val item = item("large", longName, "0.000", fruit, today.plusDays(2))
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            awaitHouseholdInventory(scenario)
            scenario.onActivity { activity ->
                val config = Configuration(activity.resources.configuration).apply { fontScale = 2f }
                @Suppress("DEPRECATION")
                activity.resources.updateConfiguration(config, activity.resources.displayMetrics)
                assertEquals(2f, activity.resources.configuration.fontScale, 0f)
                assertTrue(activity.resources.configuration.screenWidthDp <= 320)
                appendSessionFixture(activity, item)
            }
            onView(withText("Other / Uncategorized")).perform(sageScrollTo()).check(matches(isDisplayed()))
            scenario.onActivity { activity ->
                val title = text(activity.findViewById(R.id.sage_inventory_groups), "Other / Uncategorized")
                val labels = title.parent as ViewGroup
                val header = labels.parent as ViewGroup
                val count = labels.findViewById<TextView>(R.id.sage_action_subtitle)
                assertTrue(title.lineCount > 1)
                assertEquals(title.length(), title.layout.getLineEnd(title.lineCount - 1))
                assertTrue((0 until title.lineCount).all { title.layout.getEllipsisCount(it) == 0 })
                assertTrue(title.bottom <= count.top)
                assertTrue(labels.right <= header.getChildAt(2).left)
                assertTrue(labels.bottom <= header.height - header.paddingBottom)
            }
            screenshot("08-wrapped-category-320dp-200-percent")
            onView(withText("Vegetables & Fruits")).perform(sageScrollTo(), click())
            onView(withText("Out of stock")).perform(sageScrollTo()).check(matches(isDisplayed()))
            scenario.onActivity {
                val row = row(it, item)
                val advisory = text(row, "Expiring soon")
                val urgent = text(row, "Out of stock")
                assertTrue(position(urgent)[1] > position(advisory)[1])
                assertEquals(position(advisory)[0] + advisory.width, position(urgent)[0] + urgent.width)
                assertTrue(text(row, longName).lineCount > 1)
                texts(row).forEach { label ->
                    val x = position(label)[0]
                    assertTrue(x >= position(row)[0] && x + label.width <= position(row)[0] + row.width)
                    assertTrue((0 until label.lineCount).all { line -> label.layout.getEllipsisCount(line) == 0 })
                }
            }
            screenshot("07-narrow-320dp-200-percent")
            openSageInventoryDetails(item.id)
            onView(withId(R.id.sage_inventory_details)).check(matches(isDisplayed()))
        }
    }

    @Test fun previewDisclosureRemainsBesideDemoInLandscapeCategory() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            awaitHouseholdInventory(scenario)
            scenario.onActivity { it.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE }
            val deadline = SystemClock.uptimeMillis() + 5000
            var landscape = false
            while (!landscape && SystemClock.uptimeMillis() < deadline) {
                scenario.onActivity { landscape = it.resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE }
                if (!landscape) SystemClock.sleep(50)
            }
            assertTrue(landscape)
            awaitHouseholdInventory(scenario)
            val preview = InventoryItem("receipt-v53-preview", "Fixture receipt oats", 3, "Temporary receipt preview")
            scenario.onActivity { appendSessionFixture(it, preview) }
            onView(withText("Other / Uncategorized")).perform(sageScrollTo(), click())
            onView(withText("Temporary receipt preview")).perform(sageScrollTo()).check(matches(isDisplayed()))
            scenario.onActivity {
                val row = row(it, preview)
                assertTrue(row.contentDescription.contains("Temporary receipt preview"))
                val demo = it.findViewById<ViewGroup>(R.id.inventory_browse_results).findViewWithTag<View>("stock-rice")
                assertTrue(demo.contentDescription.contains("Fictional demo"))
                assertEquals(position(text(row, preview.name))[1], position(text(row, "3"))[1])
            }
            screenshot("06-demo-and-preview-landscape")
            openSageInventoryDetails(preview.id)
            onView(withText("Source: Temporary receipt preview")).check(matches(isDisplayed()))
        }
    }

    private fun item(id: String, name: String, quantity: String, category: InventoryCategory, expiry: LocalDate? = null,
        minimum: String? = null, unit: InventoryUnit = InventoryUnit.KILOGRAM) =
        InventoryItem("manual-inventory-v53-$id", name, quantity.toBigDecimal(), ManualInventoryStore.STANDALONE_ROW_STATE,
            unit, InventoryMetadata(category, expiry, minimum?.toBigDecimal()))

    private fun row(activity: MainActivity, item: InventoryItem): View =
        activity.findViewById<ViewGroup>(R.id.inventory_browse_results).findViewWithTag(item.id)

    private fun texts(view: View): List<TextView> = when (view) {
        is TextView -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { texts(view.getChildAt(it)) }
        else -> emptyList()
    }

    private fun text(view: View, value: String): TextView = texts(view).single { it.text.toString() == value }

    private fun position(view: View) = IntArray(2).also(view::getLocationOnScreen)

    private fun assertCategoryHeaders(activity: MainActivity, expanded: String? = null) {
        val groups = activity.findViewById<ViewGroup>(R.id.sage_inventory_groups)
        val titles = texts(groups).filter { it.id == R.id.sage_action_title }
        val metrics = activity.resources.displayMetrics
        fun dp(value: Int) = (value * metrics.density + 0.5f).toInt()
        assertEquals(6, titles.size)
        val cards = titles.map { title ->
            val labels = title.parent as ViewGroup
            val header = labels.parent as ViewGroup
            val isExpanded = title.text.toString() == expanded
            val count = labels.findViewById<TextView>(R.id.sage_action_subtitle)
            val icon = header.getChildAt(0)
            val chevron = header.getChildAt(2)
            assertTextSize(title, 18f)
            assertTrue(title.typeface.isBold)
            assertEquals(activity.getColor(R.color.pantry_on_surface), title.currentTextColor)
            assertTextSize(count, 14f)
            assertEquals(dp(4), header.paddingTop)
            assertEquals(dp(4), header.paddingBottom)
            assertEquals(dp(16), labels.paddingStart)
            assertEquals(dp(40), icon.width)
            assertEquals(dp(40), icon.height)
            assertEquals(dp(24), chevron.width)
            assertEquals(dp(24), chevron.height)
            for (child in listOf(icon, labels, chevron)) {
                assertTrue(kotlin.math.abs(child.top * 2 + child.height - header.height) <= 1)
            }
            assertEquals(activity.getString(if (isExpanded) R.string.sage_expanded else R.string.sage_collapsed),
                ViewCompat.getStateDescription(header))
            assertFalse(header.isPressed || header.isSelected || header.isActivated)
            header.parent as View
        }
        cards.zipWithNext { first, second ->
            assertEquals(10 * metrics.density, (second.top - first.bottom).toFloat(), 1f)
        }
    }

    private fun assertTextSize(view: TextView, sp: Float) {
        val pixels = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, sp, view.resources.displayMetrics)
        assertEquals(pixels, view.textSize, 0.5f)
    }

    private fun assertLabel(view: TextView, background: String, ink: String) {
        assertEquals(Color.parseColor(ink), view.currentTextColor)
        assertEquals(Color.parseColor(background), (view.background as GradientDrawable).color?.defaultColor)
    }

    private fun appendSessionFixture(activity: MainActivity, row: InventoryItem) {
        val field = MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }
        (field.get(activity) as PantryUiState).inventory.add(row)
        refreshInventoryFixture(activity)
    }

    private fun screenshot(name: String) {
        if (InstrumentationRegistry.getArguments().getString("sage53Screenshots") != "true") return
        instrument.waitForIdleSync()
        SystemClock.sleep(350)
        val bitmap = checkNotNull(instrument.uiAutomation.takeScreenshot())
        try {
            File(context.filesDir, "sage53-$name.png").outputStream().use {
                assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it))
            }
        } finally {
            bitmap.recycle()
        }
    }
}
