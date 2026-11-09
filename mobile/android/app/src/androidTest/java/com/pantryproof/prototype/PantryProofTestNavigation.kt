package com.pantryproof.prototype

import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId

internal fun openSyntheticPreviewFromAddReceipt() {
    onView(withId(R.id.screen_home)).check(matches(isDisplayed()))
    onView(withId(R.id.home_add_receipt)).perform(click())
    onView(withId(R.id.screen_add_receipt)).check(matches(isDisplayed()))
    onView(withId(R.id.add_use_demo)).perform(scrollTo(), click())
    onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
}

internal fun openReceiptDetails() {
    openSyntheticPreviewFromAddReceipt()
    onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
    onView(withId(R.id.screen_details)).check(matches(isDisplayed()))
}

internal fun openManualReview() {
    openReceiptDetails()
    onView(withId(R.id.details_review)).perform(scrollTo(), click())
    onView(withId(R.id.screen_review)).check(matches(isDisplayed()))
}

internal fun confirmAndOpenInventory() {
    openManualReview()
    onView(withId(R.id.review_confirm)).perform(scrollTo(), click())
    onView(withId(R.id.review_success)).check(matches(isDisplayed()))
    onView(withId(R.id.review_view_inventory)).perform(scrollTo(), click())
    onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
}
