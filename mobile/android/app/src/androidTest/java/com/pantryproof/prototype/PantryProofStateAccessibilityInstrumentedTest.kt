package com.pantryproof.prototype

import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.TextView
import android.os.ParcelFileDescriptor.AutoCloseInputStream
import android.os.SystemClock
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.closeSoftKeyboard
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isEnabled
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withContentDescription
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.hamcrest.Matchers.not
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PantryProofStateAccessibilityInstrumentedTest {
    @get:Rule
    val activityRule = ActivityScenarioRule(MainActivity::class.java)

    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun unsavedInvalidDraftDirtyStateAndBackStackSurviveRecreation() {
        openManualReview()
        onView(withId(R.id.review_store_name)).perform(scrollTo(), replaceText("Unsaved recreation"))
        onView(withId(R.id.review_purchase_date)).perform(
            scrollTo(),
            replaceText("invalid-date"),
            closeSoftKeyboard(),
        )
        onView(withId(R.id.review_status)).check(matches(withText(R.string.review_status_dirty)))

        activityRule.scenario.recreate()

        onView(withId(R.id.screen_review)).check(matches(isDisplayed()))
        onView(withId(R.id.review_store_name)).check(matches(withText("Unsaved recreation")))
        onView(withId(R.id.review_purchase_date)).check(matches(withText("invalid-date")))
        onView(withId(R.id.review_status)).check(matches(withText(R.string.review_status_dirty)))

        pressBack()
        onView(withText(R.string.review_discard_title)).check(matches(isDisplayed()))
        onView(withId(android.R.id.button1)).perform(click())
        onView(withId(R.id.screen_details)).check(matches(isDisplayed()))
    }

    @Test
    fun confirmationAndInventoryQuantitySurviveActivityRecreation() {
        openManualReview()
        onView(withId(R.id.review_store_name)).perform(scrollTo(), replaceText("Recreated Demo Store"))
        onView(withId(R.id.review_confirm)).perform(scrollTo(), closeSoftKeyboard(), click())
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))

        activityRule.scenario.recreate()
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
        onView(withId(R.id.review_store_name)).check(matches(withText("Recreated Demo Store")))

        onView(withId(R.id.review_view_inventory)).perform(scrollTo(), click())
        onView(withId(R.id.inventory_stock_rice_decrease)).perform(scrollTo(), click())
        onView(withId(R.id.inventory_stock_rice_value)).check(matches(withText("0")))

        activityRule.scenario.recreate()
        onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
        onView(withId(R.id.inventory_stock_rice_value)).check(matches(withText("0")))
        onView(withId(R.id.inventory_stock_rice_decrease)).check(matches(not(isEnabled())))

        pressBack()
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
    }

    @Test
    fun inventoryControlsEnforceBothBoundariesAndExposeDescriptions() {
        onView(withId(R.id.home_inventory)).perform(scrollTo(), click())
        onView(withId(R.id.inventory_stock_rice_decrease)).check(
            matches(withContentDescription(context.getString(
                R.string.inventory_decrease,
                "Jasmine Rice 5kg",
            ))),
        )
        onView(withId(R.id.inventory_stock_rice_increase)).check(
            matches(withContentDescription(context.getString(
                R.string.inventory_increase,
                "Jasmine Rice 5kg",
            ))),
        )

        onView(withId(R.id.inventory_stock_rice_decrease)).perform(scrollTo(), click())
        onView(withId(R.id.inventory_stock_rice_value)).check(matches(withText("0")))
        onView(withId(R.id.inventory_stock_rice_decrease)).check(matches(not(isEnabled())))

        repeat(99) {
            onView(withId(R.id.inventory_stock_rice_increase)).perform(scrollTo(), click())
        }
        onView(withId(R.id.inventory_stock_rice_value)).check(matches(withText("99")))
        onView(withId(R.id.inventory_stock_rice_increase)).check(matches(not(isEnabled())))
        onView(withId(R.id.inventory_stock_rice_decrease)).check(matches(isEnabled()))
    }

    @Test
    fun reviewLabelsAreAssociatedAndPrimaryTargetsMeetMinimumSize() {
        openManualReview()
        activityRule.scenario.onActivity { activity ->
            val root = activity.findViewById<ViewGroup>(R.id.screen_review)
            val storeField = activity.findViewById<EditText>(R.id.review_store_name)
            val dateField = activity.findViewById<EditText>(R.id.review_purchase_date)
            val confirm = activity.findViewById<View>(R.id.review_confirm)
            val back = activity.findViewById<View>(R.id.app_bar_back)
            val errorSummary = activity.findViewById<View>(R.id.review_error_summary)
            val minimum = (48 * activity.resources.displayMetrics.density).toInt()

            assertNotNull(findLabelFor(root, storeField.id))
            assertNotNull(findLabelFor(root, dateField.id))
            assertEquals(activity.getString(R.string.review_title), root.accessibilityPaneTitle)
            assertEquals(View.ACCESSIBILITY_LIVE_REGION_POLITE, errorSummary.accessibilityLiveRegion)
            assertTrue(confirm.measuredHeight >= minimum)
            assertTrue(back.measuredWidth >= minimum)
            assertTrue(back.measuredHeight >= minimum)
            assertEquals(activity.getString(R.string.navigate_back), back.contentDescription)
        }
    }

    @Test
    fun reviewRemainsUsableAtTwoHundredPercentSystemText() {
        openManualReview()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        fun executeShell(command: String): String = AutoCloseInputStream(
            automation.executeShellCommand(command),
        ).use { input -> input.bufferedReader().readText().trim() }
        fun readFontScale(): String? = executeShell("settings get system font_scale")
            .takeUnless { it.isBlank() || it == "null" }
        fun setFontScale(scale: String) {
            AutoCloseInputStream(
                automation.executeShellCommand("settings put system font_scale $scale"),
            ).use { it.readBytes() }
        }
        fun restoreFontScale(original: String?) {
            executeShell(
                if (original == null) "settings delete system font_scale"
                else "settings put system font_scale $original",
            )
        }
        fun awaitStableFontScale(expected: Float) {
            val timeoutAt = SystemClock.uptimeMillis() + 5_000
            var consecutiveMatches = 0
            var observed = Float.NaN
            while (SystemClock.uptimeMillis() < timeoutAt) {
                InstrumentationRegistry.getInstrumentation().waitForIdleSync()
                activityRule.scenario.onActivity { activity ->
                    observed = activity.resources.configuration.fontScale
                }
                consecutiveMatches = if (kotlin.math.abs(observed - expected) < 0.01f) {
                    consecutiveMatches + 1
                } else {
                    0
                }
                if (consecutiveMatches >= 3) return
                SystemClock.sleep(100)
            }
            assertEquals(expected, observed, 0.01f)
        }

        val originalFontScale = readFontScale()
        val originalConfigurationScale = originalFontScale?.toFloat() ?: 1.0f

        try {
            setFontScale("2.0")
            awaitStableFontScale(2.0f)
            activityRule.scenario.recreate()
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
            onView(withId(R.id.screen_review)).check(matches(isDisplayed()))
            onView(withId(R.id.review_store_name)).perform(scrollTo()).check(matches(isDisplayed()))
            activityRule.scenario.onActivity { activity ->
                assertEquals(2.0f, activity.resources.configuration.fontScale, 0.01f)
                val field = activity.findViewById<EditText>(R.id.review_store_name)
                assertTrue(field.lineCount >= 2)
            }
        } finally {
            restoreFontScale(originalFontScale)
            awaitStableFontScale(originalConfigurationScale)
            activityRule.scenario.recreate()
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
            assertEquals(originalFontScale, readFontScale())
            activityRule.scenario.onActivity { activity ->
                assertEquals(
                    originalConfigurationScale,
                    activity.resources.configuration.fontScale,
                    0.01f,
                )
            }
        }
    }

    private fun findLabelFor(view: View, targetId: Int): TextView? {
        if (view is TextView && view.labelFor == targetId) return view
        if (view is ViewGroup) {
            repeat(view.childCount) { index ->
                findLabelFor(view.getChildAt(index), targetId)?.let { return it }
            }
        }
        return null
    }
}
