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
import org.hamcrest.Matchers.containsString
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

        onView(withId(R.id.preview_continue)).perform(sageScrollTo(), click())
        onView(withId(R.id.screen_details)).check(matches(isDisplayed()))
        onView(withId(R.id.details_review)).perform(sageScrollTo(), click())
        onView(withId(R.id.screen_review)).check(matches(isDisplayed()))

        onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
        onView(withId(R.id.review_view_inventory)).perform(sageScrollTo(), click())
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
            "31-10-2026",
            "RM 23.00",
        ).forEach { expected ->
            onView(withText(expected)).check(matches(isDisplayed()))
        }
        onView(withId(R.id.details_item_0)).check(matches(
            hasDescendant(withText("UHT Milk 1L")),
        )).check(matches(hasDescendant(withText(containsString("Qty: 2")))))
            .check(matches(hasDescendant(withText(containsString("RM 6.50 each")))))
            .check(matches(hasDescendant(withText("RM 13.00"))))
        onView(withId(R.id.details_item_1)).check(matches(
            hasDescendant(withText("Wholemeal Bread")),
        )).check(matches(hasDescendant(withText(containsString("Qty: 1")))))
            .check(matches(hasDescendant(withText("RM 4.20"))))
        onView(withId(R.id.details_item_2)).check(matches(
            hasDescendant(withText("Bananas (bunch)")),
        )).check(matches(hasDescendant(withText(containsString("Qty: 1")))))
            .check(matches(hasDescendant(withText("RM 5.80"))))
            .check(matches(hasDescendant(withText(containsString(context.getString(R.string.v4_unit_price_optional))))))
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
        onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())

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
        onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
        openSageInventoryDetails("stock-rice")
        onView(withId(R.id.inventory_stock_rice_decrease)).perform(scrollTo(), click())
        pressBack()
        pressBack()
        openManualReview()
        onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
        pressBack()
        onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())
        onView(withId(R.id.review_view_inventory)).perform(sageScrollTo(), click())

        onView(withId(R.id.inventory_summary)).check(
            matches(withText(context.resources.getQuantityString(R.plurals.inventory_summary, 6, 6))),
        )
        openSageInventoryDetails("stock-rice")
        onView(withId(R.id.inventory_stock_rice_value)).check(matches(withText("0")))
    }
    @Test
    fun reviewRejects100AndOverflowWithoutAdmittingInventory() {
        lateinit var originalInventory: List<com.pantryproof.prototype.data.InventoryItem>
        lateinit var originalReceipt: com.pantryproof.prototype.data.Receipt
        activityRule.scenario.onActivity { activity ->
            val state = quantityState(activity)
            originalInventory = state.inventory.toList()
            originalReceipt = requireNotNull(state.receipt)
        }
        openManualReview()
        for (raw in listOf("100", "2147483648")) {
            onView(withId(R.id.review_item_0_quantity)).perform(scrollTo(), replaceText(raw), closeSoftKeyboard())
            onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())
            onView(withId(R.id.review_success)).check(doesNotExist())
            onView(withId(R.id.review_item_0_quantity)).check(matches(withText(raw)))
                .check(matches(hasErrorText(if (raw == "100") "Quantity must be 99 or less." else
                    "Quantity must be a whole number above zero.")))
            activityRule.scenario.onActivity { activity ->
                val state = quantityState(activity)
                org.junit.Assert.assertEquals(originalInventory, state.inventory)
                org.junit.Assert.assertEquals(originalReceipt, state.receipt)
                org.junit.Assert.assertFalse(state.demoConfirmed)
            }
        }
    }

    @Test
    fun reviewed98IsAdmittedExactlyAndIncrementStopsAt99() = verifyReviewedQuantityBoundary(98)

    @Test
    fun reviewed99IsAdmittedExactlyAndDecrementKeepsTheSameRow() = verifyReviewedQuantityBoundary(99)

    private fun verifyReviewedQuantityBoundary(quantity: Int) {
        lateinit var rowId: String
        lateinit var baseline: List<com.pantryproof.prototype.data.InventoryItem>
        activityRule.scenario.onActivity { activity ->
            val state = quantityState(activity)
            rowId = "receipt-${requireNotNull(state.receipt).items[0].id}"
            baseline = state.inventory.toList()
        }
        openManualReview()
        onView(withId(R.id.review_item_0_quantity)).perform(scrollTo(), replaceText(quantity.toString()), closeSoftKeyboard())
        onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())
        onView(withId(R.id.review_success)).check(matches(isDisplayed()))
        onView(withId(R.id.review_view_inventory)).perform(sageScrollTo(), click())
        val increase = androidx.test.espresso.matcher.ViewMatchers.withTagValue(org.hamcrest.CoreMatchers.equalTo("inventory-increase:$rowId"))
        val decrease = androidx.test.espresso.matcher.ViewMatchers.withTagValue(org.hamcrest.CoreMatchers.equalTo("inventory-decrease:$rowId"))
        fun assertQuantity(expected: Int) {
            activityRule.scenario.onActivity { activity ->
                val state = quantityState(activity)
                org.junit.Assert.assertEquals(expected, state.inventory.single { it.id == rowId }.quantity)
                org.junit.Assert.assertEquals(baseline, state.inventory.filterNot { it.id.startsWith("receipt-") })
                val results = activity.findViewById<android.view.ViewGroup>(R.id.inventory_browse_results)
                val row = requireNotNull(results.findViewWithTag<android.view.View>(rowId))
                fun hasQuantity(view: android.view.View): Boolean = when (view) {
                    is android.widget.TextView -> view.text.toString() == expected.toString()
                    is android.view.ViewGroup -> (0 until view.childCount).any { hasQuantity(view.getChildAt(it)) }
                    else -> false
                }
                org.junit.Assert.assertTrue("The exact row must display $expected", hasQuantity(row))
            }
        }
        assertQuantity(quantity)
        openSageInventoryDetails(rowId)
        if (quantity == 98) {
            onView(increase).perform(scrollTo(), click())
            assertQuantity(99)
        }
        onView(increase).check(matches(org.hamcrest.CoreMatchers.not(androidx.test.espresso.matcher.ViewMatchers.isEnabled())))
        onView(decrease).perform(scrollTo(), click())
        assertQuantity(98)
        onView(increase).check(matches(androidx.test.espresso.matcher.ViewMatchers.isEnabled()))
    }

    private fun quantityState(activity: MainActivity): com.pantryproof.prototype.ui.PantryUiState =
        MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }
            .get(activity) as com.pantryproof.prototype.ui.PantryUiState

}
