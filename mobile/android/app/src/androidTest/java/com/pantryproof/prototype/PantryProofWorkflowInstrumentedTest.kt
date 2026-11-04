package com.pantryproof.prototype

import android.widget.EditText
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.closeSoftKeyboard
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.hasErrorText
import androidx.test.espresso.matcher.ViewMatchers.hasDescendant
import androidx.test.espresso.matcher.ViewMatchers.hasFocus
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.Visibility
import androidx.test.espresso.matcher.ViewMatchers.withEffectiveVisibility
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PantryProofWorkflowInstrumentedTest {
    @get:Rule
    val activityRule = ActivityScenarioRule(MainActivity::class.java)

    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun completeSyntheticJourneyAndBackNavigation() {
        openSyntheticPreviewFromAddReceipt()
        onView(withText(R.string.preview_synthetic_status)).check(matches(isDisplayed()))
        onView(withText("Process receipt")).check(doesNotExist())

        onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
        onView(withId(R.id.screen_details)).check(matches(isDisplayed()))
        onView(withId(R.id.details_review)).perform(scrollTo(), click())
        onView(withId(R.id.screen_review)).check(matches(isDisplayed()))

        onView(withId(R.id.review_confirm)).perform(scrollTo(), click())
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
        onView(withId(R.id.review_view_inventory)).perform(scrollTo(), click())
        onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))

        pressBack()
        onView(withId(R.id.screen_review)).check(matches(isDisplayed()))
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
    }

    @Test
    fun receiptDetailsDisplayAllDeterministicFieldsAndRinggitFormatting() {
        openReceiptDetails()

        listOf(
            "Demo Grocery Store (Synthetic)",
            "31 October 2026",
            "RM 23.00",
        ).forEach { expected ->
            onView(withText(expected)).check(matches(isDisplayed()))
        }
        onView(withId(R.id.details_item_0)).check(matches(
            hasDescendant(withText("UHT Milk 1L")),
        )).check(matches(hasDescendant(withText("2"))))
            .check(matches(hasDescendant(withText("RM 6.50"))))
            .check(matches(hasDescendant(withText("RM 13.00"))))
        onView(withId(R.id.details_item_1)).check(matches(
            hasDescendant(withText("Wholemeal Bread")),
        )).check(matches(hasDescendant(withText("1"))))
            .check(matches(hasDescendant(withText("RM 4.20"))))
        onView(withId(R.id.details_item_2)).check(matches(
            hasDescendant(withText("Bananas (bunch)")),
        )).check(matches(hasDescendant(withText("1"))))
            .check(matches(hasDescendant(withText("RM 5.80"))))
            .check(matches(hasDescendant(withText(R.string.details_unit_price_missing))))
    }

    @Test
    fun invalidManualReviewShowsSummaryAndFocusesFirstInvalidField() {
        openManualReview()

        onView(withId(R.id.review_store_name)).perform(scrollTo(), replaceText(""))
        onView(withId(R.id.review_purchase_date)).perform(scrollTo(), replaceText("31/10/2026"))
        onView(withId(R.id.review_item_0_quantity)).perform(scrollTo(), replaceText("0"))
        onView(withId(R.id.review_item_0_line_total)).perform(scrollTo(), replaceText("not-a-number"))
        onView(withId(R.id.review_item_1_line_total)).perform(scrollTo(), replaceText("-4.20"))
        onView(withId(R.id.review_item_2_unit_price)).perform(scrollTo(), replaceText(""))
        onView(withId(R.id.review_receipt_total)).perform(
            scrollTo(),
            replaceText("1.234"),
            closeSoftKeyboard(),
        )
        onView(withId(R.id.review_confirm)).perform(scrollTo(), click())

        onView(withId(R.id.review_error_summary)).check(
            matches(withEffectiveVisibility(Visibility.VISIBLE)),
        )
        onView(withId(R.id.review_success)).check(doesNotExist())
        onView(withId(R.id.review_store_name)).check(matches(hasFocus()))
        onView(withId(R.id.review_store_name)).check(matches(hasErrorText("Store name is required.")))
        onView(withId(R.id.review_purchase_date)).check(
            matches(hasErrorText("Use a valid date in YYYY-MM-DD format.")),
        )
        onView(withId(R.id.review_item_0_quantity)).check(
            matches(hasErrorText("Quantity must be a whole number above zero.")),
        )
        onView(withId(R.id.review_item_0_line_total)).check(
            matches(hasErrorText("Enter a non-negative amount, for example 6.50.")),
        )
        onView(withId(R.id.review_item_1_line_total)).check(
            matches(hasErrorText("Enter a non-negative amount, for example 6.50.")),
        )
        onView(withId(R.id.review_receipt_total)).check(
            matches(hasErrorText("Use no more than two decimal places.")),
        )
        activityRule.scenario.onActivity { activity ->
            assertNull(activity.findViewById<EditText>(R.id.review_item_2_unit_price).error)
        }
    }

    @Test
    fun temporaryApplyDiscardCancelAndRevertPreserveExpectedValues() {
        openManualReview()
        onView(withId(R.id.review_store_name)).perform(scrollTo(), replaceText("Applied Demo Store"))
        onView(withId(R.id.review_status)).check(matches(withText(R.string.review_status_dirty)))
        onView(withId(R.id.review_apply)).perform(scrollTo(), closeSoftKeyboard(), click())
        onView(withId(R.id.review_status)).check(matches(withText(R.string.review_status_saved)))

        onView(withId(R.id.review_store_name)).perform(scrollTo(), replaceText("Unsaved Demo Store"))
        onView(withId(R.id.review_discard)).perform(scrollTo(), closeSoftKeyboard(), click())
        onView(withText(R.string.review_discard_title)).check(matches(isDisplayed()))
        onView(withId(android.R.id.button2)).perform(click())
        onView(withId(R.id.review_store_name)).check(matches(withText("Unsaved Demo Store")))

        onView(withId(R.id.review_discard)).perform(scrollTo(), click())
        onView(withId(android.R.id.button1)).perform(click())
        onView(withId(R.id.review_store_name)).check(matches(withText("Applied Demo Store")))

        onView(withId(R.id.review_revert)).perform(scrollTo(), click())
        onView(withText(R.string.review_revert_title)).check(matches(isDisplayed()))
        onView(withId(android.R.id.button1)).perform(click())
        onView(withId(R.id.review_store_name)).check(
            matches(withText("Demo Grocery Store (Synthetic)")),
        )
        onView(withId(R.id.review_success)).check(doesNotExist())
    }

    @Test
    fun repeatedConfirmationDoesNotDuplicateInventoryRows() {
        onView(withId(R.id.home_inventory)).perform(scrollTo(), click())
        onView(withId(R.id.inventory_stock_rice_decrease)).perform(scrollTo(), click())
        pressBack()
        openManualReview()
        onView(withId(R.id.review_confirm)).perform(scrollTo(), click())
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
        onView(withId(R.id.review_confirm)).perform(scrollTo(), click())
        onView(withId(R.id.review_view_inventory)).perform(scrollTo(), click())

        onView(withId(R.id.inventory_summary)).check(
            matches(withText(context.resources.getQuantityString(R.plurals.inventory_summary, 6, 6))),
        )
        onView(withId(R.id.inventory_stock_rice_value)).check(matches(withText("0")))
    }
}
